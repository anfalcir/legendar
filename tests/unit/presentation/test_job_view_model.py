from __future__ import annotations

from legendar.domain.events.job_events import (
    JobCancelled,
    JobCompleted,
    JobFailed,
    JobStarted,
    LogRecorded,
    ProgressReported,
    StateChanged,
)
from legendar.domain.state.machine import JobState
from legendar.presentation.qt.view_model.job_view_model import (
    MAX_LOG_LINES,
    JobViewModel,
)


def _state(sequence: int, previous: JobState, current: JobState) -> StateChanged:
    return StateChanged("job-1", sequence, previous=previous, current=current)


def test_starts_idle_and_ready() -> None:
    snapshot = JobViewModel().snapshot

    assert snapshot.state is JobState.IDLE
    assert snapshot.progress_percent == 0
    assert snapshot.can_start
    assert not snapshot.can_cancel
    assert not snapshot.is_running


def test_job_started_names_the_source() -> None:
    vm = JobViewModel()
    vm.apply(_state(1, JobState.IDLE, JobState.VALIDATING_INPUT))

    snapshot = vm.apply(JobStarted("job-1", 2, source_label="aula.mp4"))

    assert "aula.mp4" in snapshot.status_text
    assert snapshot.is_running
    assert not snapshot.can_start


def test_active_state_exposes_cancel_and_hides_start() -> None:
    vm = JobViewModel()
    vm.apply(_state(1, JobState.IDLE, JobState.VALIDATING_INPUT))

    snapshot = vm.apply(_state(2, JobState.VALIDATING_INPUT, JobState.TRANSCRIBING))

    assert snapshot.state is JobState.TRANSCRIBING
    assert snapshot.status_text == "Transcrevendo"
    assert snapshot.can_cancel
    assert not snapshot.can_start


def test_publishing_is_not_cancellable() -> None:
    vm = JobViewModel()
    vm.apply(_state(1, JobState.IDLE, JobState.VALIDATING_INPUT))

    snapshot = vm.apply(_state(2, JobState.VALIDATING_INPUT, JobState.PUBLISHING))

    assert snapshot.is_running
    assert not snapshot.can_cancel


def test_progress_never_regresses_and_uses_message() -> None:
    vm = JobViewModel()
    vm.apply(_state(1, JobState.IDLE, JobState.VALIDATING_INPUT))
    vm.apply(_state(2, JobState.VALIDATING_INPUT, JobState.PREPARING_AUDIO))
    vm.apply(ProgressReported("job-1", 3, fraction=0.4, message="Preparando"))
    snapshot = vm.apply(ProgressReported("job-1", 4, fraction=0.2, message="Tarde"))

    assert snapshot.progress == 0.4
    assert snapshot.progress_percent == 40
    assert snapshot.status_text == "Tarde"


def test_progress_without_message_keeps_current_status() -> None:
    vm = JobViewModel()
    vm.apply(_state(1, JobState.IDLE, JobState.VALIDATING_INPUT))
    vm.apply(_state(2, JobState.VALIDATING_INPUT, JobState.ALIGNING))

    snapshot = vm.apply(ProgressReported("job-1", 3, fraction=0.5))

    assert snapshot.status_text == "Alinhando"


def test_log_lines_are_appended_and_prefixed_by_level() -> None:
    vm = JobViewModel()
    vm.apply(LogRecorded("job-1", 1, level="info", message="Iniciando"))
    snapshot = vm.apply(
        LogRecorded("job-1", 2, level="warning", message="Faixa alternativa")
    )

    assert snapshot.log_lines == ("Iniciando", "Aviso: Faixa alternativa")


def test_log_is_bounded() -> None:
    vm = JobViewModel()
    for sequence in range(1, MAX_LOG_LINES + 10):
        vm.apply(LogRecorded("job-1", sequence, message=f"linha {sequence}"))

    lines = vm.snapshot.log_lines

    assert len(lines) == MAX_LOG_LINES
    assert lines[-1] == f"linha {MAX_LOG_LINES + 9}"
    assert lines[0] == "linha 10"


def test_out_of_order_and_duplicate_events_are_ignored() -> None:
    vm = JobViewModel()
    vm.apply(_state(5, JobState.IDLE, JobState.VALIDATING_INPUT))
    snapshot = vm.apply(_state(2, JobState.VALIDATING_INPUT, JobState.TRANSCRIBING))

    assert snapshot.state is JobState.VALIDATING_INPUT


def test_completion_is_terminal_and_exposes_output() -> None:
    vm = JobViewModel()
    vm.apply(_state(1, JobState.IDLE, JobState.VALIDATING_INPUT))
    vm.apply(_state(2, JobState.VALIDATING_INPUT, JobState.PUBLISHING))

    snapshot = vm.apply(
        JobCompleted("job-1", 3, output_path="/tmp/aula.srt", cue_count=12)
    )

    assert snapshot.progress_percent == 100
    assert snapshot.is_finished
    assert snapshot.can_start
    assert snapshot.output_path == "/tmp/aula.srt"
    assert "Concluído com 12" in snapshot.log_lines[-1]
    ignored = vm.apply(JobFailed("job-1", 4, message="tarde demais"))
    assert ignored.state is JobState.COMPLETED


def test_failure_exposes_message_and_allows_restart() -> None:
    vm = JobViewModel()
    vm.apply(_state(1, JobState.IDLE, JobState.VALIDATING_INPUT))
    vm.apply(_state(2, JobState.VALIDATING_INPUT, JobState.PREPARING_AUDIO))

    snapshot = vm.apply(JobFailed("job-1", 3, message="ffprobe não encontrado"))

    assert snapshot.error_message == "ffprobe não encontrado"
    assert "Falha:" in snapshot.status_text
    assert snapshot.is_finished
    assert snapshot.can_start


def test_cancellation_exposes_message() -> None:
    vm = JobViewModel()
    vm.apply(_state(1, JobState.IDLE, JobState.VALIDATING_INPUT))
    vm.apply(_state(2, JobState.VALIDATING_INPUT, JobState.ALIGNING))

    snapshot = vm.apply(JobCancelled("job-1", 3, message="Cancelado pelo usuário."))

    assert snapshot.state is JobState.CANCELLED
    assert snapshot.status_text == "Cancelado pelo usuário."
    assert snapshot.can_start



def test_operational_warning_survives_rerender_after_terminal_event() -> None:
    vm = JobViewModel()
    vm.apply(_state(1, JobState.IDLE, JobState.VALIDATING_INPUT))
    vm.apply(JobFailed("job-1", 2, message="falha controlada"))

    snapshot = vm.report_warning("não foi possível limpar o diretório temporário")

    assert snapshot.state is JobState.FAILED
    assert snapshot.error_message == "falha controlada"
    assert snapshot.status_text == "Falha: falha controlada"
    assert snapshot.log_lines[-1] == (
        "Aviso: não foi possível limpar o diretório temporário"
    )


def test_reset_clears_everything() -> None:
    vm = JobViewModel()
    vm.apply(LogRecorded("job-1", 1, message="oi"))
    vm.apply(_state(2, JobState.IDLE, JobState.VALIDATING_INPUT))

    snapshot = vm.reset()

    assert snapshot.state is JobState.IDLE
    assert snapshot.log_lines == ()
    assert snapshot.progress == 0.0
