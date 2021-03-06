import optparse
import pickle
import random
import sys
import traceback

class WritableNull:
    def write(self, string):
        pass

    def flush(self):
        pass

class Tracker(object):
    def __init__(self, questions, maxes, prereqs, mute_output):
        self.questions = questions
        self.maxes = maxes
        self.prereqs = prereqs

        self.points = {q: 0 for q in self.questions}

        self.current_question = None

        self.current_test = None
        self.points_at_test_start = None
        self.possible_points_remaining = None

        self.mute_output = mute_output
        self.original_stdout = None
        self.muted = False

    def mute(self):
        if self.muted:
            return

        self.muted = True
        self.original_stdout = sys.stdout
        sys.stdout = WritableNull()

    def unmute(self):
        if not self.muted:
            return

        self.muted = False
        sys.stdout = self.original_stdout

    def begin_q(self, q):
        assert q in self.questions
        self.current_question = q
        self.possible_points_remaining = self.maxes[q]
        return True

    def begin_test(self, test_name):
        self.current_test = test_name
        self.points_at_test_start = self.points[self.current_question]
        print("*** {}) {}".format(self.current_question, self.current_test))
        if self.mute_output:
            self.mute()

    def end_test(self, pts):
        if self.mute_output:
            self.unmute()
        self.possible_points_remaining -= pts
        if self.points[self.current_question] == self.points_at_test_start + pts:
            print("*** PASS: {}".format(self.current_test))
        elif self.points[self.current_question] == self.points_at_test_start:
            print("*** FAIL")

        self.current_test = None
        self.points_at_test_start = None

    def end_q(self):
        assert self.current_question is not None
        assert self.possible_points_remaining == 0
        self.current_question = None
        self.possible_points_remaining = None

    def add_points(self, pts):
        self.points[self.current_question] += pts

TESTS = []
PREREQS = {}
def add_prereq(q, pre):
    if isinstance(pre, str):
        pre = [pre]

    if q not in PREREQS:
        PREREQS[q] = set()
    PREREQS[q] |= set(pre)

def test(q, points):
    def deco(fn):
        TESTS.append((q, points, fn))
        return fn
    return deco

def main():

    disable_graphics()

    questions = set()
    maxes = {}
    for q, points, fn in TESTS:
        questions.add(q)
        maxes[q] = maxes.get(q, 0) + points
        if q not in PREREQS:
            PREREQS[q] = set()

    questions = list(sorted(questions))
    tracker = Tracker(questions, maxes, PREREQS, False)
    for q in questions:
        started = tracker.begin_q(q)
        if not started:
            continue

        for testq, points, fn in TESTS:
            if testq != q:
                continue
            try:
                fn(tracker)
            except KeyboardInterrupt:
                tracker.unmute()
                sys.exit(1)
            except:
                tracker.unmute()
        tracker.end_q()

################################################################################
# Tests begin here
################################################################################

import numpy as np
import matplotlib
import contextlib

import nn
import backend

def check_dependencies():
    import matplotlib.pyplot as plt
    import time
    fig, ax = plt.subplots(1, 1)
    ax.set_xlim([-1, 1])
    ax.set_ylim([-1, 1])
    line, = ax.plot([], [], color="black")
    plt.show(block=False)

    for t in range(400):
        angle = t * 0.05
        x = np.sin(angle)
        y = np.cos(angle)
        line.set_data([x,-x], [y,-y])
        fig.canvas.draw_idle()
        fig.canvas.start_event_loop(1e-3)

def disable_graphics():
    backend.use_graphics = False

@contextlib.contextmanager
def no_graphics():
    old_use_graphics = backend.use_graphics
    backend.use_graphics = False
    yield
    backend.use_graphics = old_use_graphics

def verify_node(node, expected_type, expected_shape, method_name):
    if expected_type == 'parameter':
        assert node is not None, (
            "{} should return an instance of nn.Parameter, not None".format(method_name))
        assert isinstance(node, nn.Parameter), (
            "{} should return an instance of nn.Parameter, instead got type {!r}".format(
            method_name, type(node).__name__))
    elif expected_type == 'loss':
        assert node is not None, (
            "{} should return an instance a loss node, not None".format(method_name))
        assert isinstance(node, (nn.SquareLoss, nn.SoftmaxLoss)), (
            "{} should return a loss node, instead got type {!r}".format(
            method_name, type(node).__name__))
    elif expected_type == 'node':
        assert node is not None, (
            "{} should return a node object, not None".format(method_name))
        assert isinstance(node, nn.Node), (
            "{} should return a node object, instead got type {!r}".format(
            method_name, type(node).__name__))
    else:
        assert False, "If you see this message, please report a bug in the autograder"

    if expected_type != 'loss':
        assert all([(expected == '?' or actual == expected) for (actual, expected) in zip(node.data.shape, expected_shape)]), (
            "{} should return an object with shape {}, got {}".format(
                method_name, nn.format_shape(expected_shape), nn.format_shape(node.data.shape)))

def trace_node(node_to_trace):
    """
    Returns a set containing the node and all ancestors in the computation graph
    """
    nodes = set()
    tape = []

    def visit(node):
        if node not in nodes:
            for parent in node.parents:
                visit(parent)
            nodes.add(node)
            tape.append(node)

    visit(node_to_trace)

    return nodes


@test('q3', points=6)
def check_digit_classification(tracker):
    import models
    model = models.DigitClassificationModel()
    dataset = backend.DigitClassificationDataset(model)

    detected_parameters = None
    for batch_size in (1, 2, 4):
        inp_x = nn.Constant(dataset.x[:batch_size])
        inp_y = nn.Constant(dataset.y[:batch_size])
        output_node = model.run(inp_x)
        verify_node(output_node, 'node', (batch_size, 10), "DigitClassificationModel.run()")
        trace = trace_node(output_node)
        assert inp_x in trace, "Node returned from DigitClassificationModel.run() does not depend on the provided input (x)"

        if detected_parameters is None:
            detected_parameters = [node for node in trace if isinstance(node, nn.Parameter)]

        for node in trace:
            assert not isinstance(node, nn.Parameter) or node in detected_parameters, (
                "Calling DigitClassificationModel.run() multiple times should always re-use the same parameters, but a new nn.Parameter object was detected")

    for batch_size in (1, 2, 4):
        inp_x = nn.Constant(dataset.x[:batch_size])
        inp_y = nn.Constant(dataset.y[:batch_size])
        loss_node = model.get_loss(inp_x, inp_y)
        verify_node(loss_node, 'loss', None, "DigitClassificationModel.get_loss()")
        trace = trace_node(loss_node)
        assert inp_x in trace, "Node returned from DigitClassificationModel.get_loss() does not depend on the provided input (x)"
        assert inp_y in trace, "Node returned from DigitClassificationModel.get_loss() does not depend on the provided labels (y)"

        for node in trace:
            assert not isinstance(node, nn.Parameter) or node in detected_parameters, (
                "DigitClassificationModel.get_loss() should not use additional parameters not used by DigitClassificationModel.run()")

    tracker.add_points(2) # Partial credit for passing sanity checks

    model.train(dataset)

    test_logits = model.run(nn.Constant(dataset.test_images)).data
    test_predicted = np.argmax(test_logits, axis=1)
    test_accuracy = np.mean(test_predicted == dataset.test_labels)

    accuracy_threshold = 0.97
    if test_accuracy >= accuracy_threshold:
        print("Your final test set accuracy is: {:%}".format(test_accuracy))
        tracker.add_points(4)
    else:
        print("Your final test set accuracy ({:%}) must be at least {:.0%} to receive full points for this question".format(test_accuracy, accuracy_threshold))


if __name__ == '__main__':
    main()
