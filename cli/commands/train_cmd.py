import typer
from pathlib import Path
from rich.console import Console
from rich.table import Table

console = Console()

_DEFAULT_LABELS = Path(__file__).parent.parent.parent / "data" / "intent_labels.jsonl"


def train_intent(
    labels: Path = typer.Option(
        _DEFAULT_LABELS,
        "--labels", "-l",
        help="Path to intent_labels.jsonl training file.",
        exists=True,
    ),
    eval: bool = typer.Option(
        True,
        "--eval/--no-eval",
        help="Run 5-fold cross-validation and report accuracy.",
    ),
):
    """Train the ML intent classifier on labeled query examples."""
    try:
        from core.ml_intent_classifier import MLIntentClassifier
    except ImportError:
        console.print("[red]scikit-learn is required: uv pip install -e '.[ml]'[/red]")
        raise typer.Exit(1)

    console.print(f"  Loading labels from [bold]{labels}[/bold]...")
    clf = MLIntentClassifier()

    try:
        result = clf.train(str(labels), eval_cv=eval)
    except Exception as e:
        console.print(f"[red]Training failed: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"\n[green]Trained on {result['n_train']} examples.[/green]")

    t = Table(show_header=True, header_style="bold cyan")
    t.add_column("Metric")
    t.add_column("Value")
    t.add_row("Examples", str(result["n_train"]))
    t.add_row("Classes", ", ".join(result["classes"]))
    if result["cv_accuracy"] is not None:
        accuracy_pct = f"{result['cv_accuracy'] * 100:.1f}%"
        color = "green" if result["cv_accuracy"] >= 0.80 else "yellow"
        t.add_row("CV Accuracy (5-fold)", f"[{color}]{accuracy_pct}[/{color}]")
    else:
        t.add_row("CV Accuracy", "skipped (--no-eval)")

    console.print(t)
    console.print("\nModel saved. The intent classifier will use ML on next query.")
