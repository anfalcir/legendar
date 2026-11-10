"""Testes da máquina de estados: fluxo felizes, desvios e estados terminais."""

from __future__ import annotations

import pytest

from legendar.domain.errors.catalog import InvalidTransitionError
from legendar.domain.state.machine import (
    PIPELINE_SEQUENCE,
    JobState,
    StateMachine,
    can_transition,
)


def test_full_pipeline_sequence_is_legal():
    machine = StateMachine()
    machine.transition(JobState.VALIDATING_INPUT)
    for state in PIPELINE_SEQUENCE[1:]:
        machine.transition(state)
    assert machine.state is JobState.COMPLETED
    assert machine.state.is_terminal


def test_segmenting_may_skip_translation():
    assert can_transition(JobState.SEGMENTING, JobState.VALIDATING_SRT)
    assert can_transition(JobState.SEGMENTING, JobState.TRANSLATING)


def test_import_from_idle_restarts_after_terminal_state():
    machine = StateMachine()
    machine.transition(JobState.VALIDATING_INPUT)
    machine.transition(JobState.INSPECTING_MEDIA)
    machine.transition(JobState.FAILED)
    machine.reset()
    assert machine.state is JobState.IDLE
    machine.transition(JobState.VALIDATING_INPUT)


def test_terminal_states_only_allow_explicit_restart():
    for terminal in (JobState.COMPLETED, JobState.CANCELLED, JobState.FAILED):
        assert not can_transition(terminal, JobState.IDLE)
        assert not can_transition(terminal, JobState.TRANSCRIBING)
        assert can_transition(terminal, JobState.VALIDATING_INPUT)


def test_publishing_cannot_be_cancelled():
    assert not JobState.PUBLISHING.is_cancellable
    assert not can_transition(JobState.PUBLISHING, JobState.CANCELLING)


@pytest.mark.parametrize(
    "state",
    [
        state
        for state in JobState
        if state.is_active and state is not JobState.PUBLISHING
    ],
)
def test_active_states_can_be_cancelled(state: JobState):
    assert can_transition(state, JobState.CANCELLING)


def test_skipping_stage_raises_invalid_transition():
    machine = StateMachine()
    with pytest.raises(InvalidTransitionError):
        machine.transition(JobState.TRANSCRIBING)


def test_self_transition_is_forbidden():
    assert not can_transition(JobState.ALIGNING, JobState.ALIGNING)


def test_history_records_transitions():
    machine = StateMachine()
    machine.transition(JobState.VALIDATING_INPUT)
    machine.transition(JobState.INSPECTING_MEDIA, reason="teste")
    assert [change.target for change in machine.history] == [
        JobState.VALIDATING_INPUT,
        JobState.INSPECTING_MEDIA,
    ]
    assert machine.history[-1].reason == "teste"
