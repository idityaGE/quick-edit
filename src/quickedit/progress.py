"""
Rich-based progress bar display for the QuickEdit pipeline.

Shows a live multi-step progress bar in the terminal during processing.
Each pipeline step (VAD, motion, transcription, etc.) gets its own bar
that fills as progress is reported.
"""

from __future__ import annotations

from rich.console import Console
from rich.progress import (
    BarColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TaskProgressColumn,
    TextColumn,
    TimeElapsedColumn,
)

# Map internal step names to friendly display labels
STEP_LABELS: dict[str, str] = {
    "vad": "🎙  Voice Detection",
    "motion": "🎬  Motion Detection",
    "transcription": "📝  Transcription",
    "combine": "🔗  Combining Signals",
    "llm": "🤖  LLM Analysis",
    "subtitles": "💬  Subtitles",
    "render": "🎞  Rendering",
}

# Steps in execution order (used to pre-create tasks)
STEP_ORDER = ["vad", "motion", "transcription", "combine", "llm", "subtitles", "render"]


class ProgressReporter:
    """
    Manages a rich Progress display for the pipeline.

    Usage:
        reporter = ProgressReporter()
        config.progress_callback = reporter.callback
        with reporter:
            result = run_pipeline(config)

    The callback signature matches PipelineConfig.progress_callback:
        (step: str, progress: float, message: str) -> None
    """

    def __init__(self, console: Console | None = None) -> None:
        self.console = console or Console()
        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.fields[icon]}[/]"),
            TextColumn("[bold]{task.description}[/]", justify="left"),
            BarColumn(
                bar_width=30, complete_style="green", finished_style="bright_green"
            ),
            TaskProgressColumn(),
            TextColumn("[dim]{task.fields[message]}[/]"),
            TimeElapsedColumn(),
            console=self.console,
            expand=False,
            transient=False,
        )
        self._tasks: dict[str, TaskID] = {}

    def __enter__(self) -> ProgressReporter:
        self._progress.__enter__()
        return self

    def __exit__(self, *args) -> None:
        self._progress.__exit__(*args)

    def _get_or_create_task(self, step: str) -> TaskID:
        """Get existing task ID or create a new one for this step."""
        if step not in self._tasks:
            label = STEP_LABELS.get(step, step.title())
            icon = label.split(" ")[0] if " " in label else "⚙"
            desc = label.split("  ", 1)[-1] if "  " in label else label
            task_id = self._progress.add_task(
                desc,
                total=100,
                icon=icon,
                message="Starting...",
            )
            self._tasks[step] = task_id
        return self._tasks[step]

    def callback(self, step: str, progress: float, message: str = "") -> None:
        """
        Progress callback for the pipeline.

        Args:
            step: Pipeline step name (e.g., "transcription", "vad").
            progress: Progress value between 0.0 and 1.0.
            message: Human-readable status message.
        """
        task_id = self._get_or_create_task(step)
        completed = min(int(progress * 100), 100)

        self._progress.update(
            task_id,
            completed=completed,
            message=message or "",
        )

    def finish_step(self, step: str, message: str = "Done") -> None:
        """Mark a step as fully complete."""
        if step in self._tasks:
            self._progress.update(
                self._tasks[step],
                completed=100,
                message=f"[green]{message}[/]",
            )
