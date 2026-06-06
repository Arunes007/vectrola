"""Vectrola CLI - Multimodal Music Knowledge Graph."""

import typer
from pathlib import Path
from typing import Optional

from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table
from rich import print as rprint

app = typer.Typer(
    name="vectrola",
    help="🎧 Vectrola: Multimodal Music Knowledge Graph\n\nSemantic music search using audio embeddings and LLM synthesis.",
    add_completion=False,
)
console = Console()


@app.command()
def ingest(
    path: Path = typer.Argument(..., help="File or directory to ingest"),
    recursive: bool = typer.Option(True, "--recursive/--no-recursive", "-r/-R", help="Scan subdirectories"),
    fast: bool = typer.Option(True, "--fast/--slow", "-f/-s", help="Skip Demucs stem separation (faster)"),
    write_tags: bool = typer.Option(True, "--tags/--no-tags", help="Write analysis to file tags"),
):
    """
    Ingest audio files into the knowledge graph.

    Transcribes lyrics and extracts semantic metadata (themes, moods, narrative).
    """
    from vectrola.ingest.pipeline import IngestPipeline

    # Collect files to process
    if path.is_file():
        files = [path]
    else:
        pattern = "**/*" if recursive else "*"
        files = []
        for ext in [".mp3", ".flac", ".wav", ".m4a", ".ogg"]:
            files.extend(path.glob(f"{pattern}{ext}"))
            files.extend(path.glob(f"{pattern}{ext.upper()}"))

    if not files:
        print("⚠️  No audio files found.")
        raise typer.Exit(1)

    total = len(files)
    print(f"🎧 Found {total} audio file(s)")

    if fast:
        print("   Fast mode: skipping Demucs vocal separation")
    print()

    pipeline = IngestPipeline(use_stems=not fast)

    # Process files with simple progress
    results = []
    errors = []

    for i, file in enumerate(files, 1):
        print(f"[{i}/{total}] {file.name}", flush=True)
        try:
            result = pipeline.process_track(file, write_file_tags=write_tags)
            results.append(result)
            moods_str = ", ".join(result.moods[:3]) if result.moods else "no moods"
            print(f"   ✓ Done: {moods_str}")

        except Exception as e:
            errors.append((file, str(e)))
            print(f"   ✗ Error: {e}")

    # Summary
    print()
    print(f"✅ Processed: {len(results)} tracks")
    if errors:
        print(f"❌ Errors: {len(errors)} tracks")


@app.command()
def analyze(
    file: Path = typer.Argument(..., help="Audio file to analyze"),
):
    """
    Analyze a single audio file and show detailed results.

    Does NOT write to file tags - use 'ingest' for that.
    """
    from vectrola.ingest.pipeline import IngestPipeline

    if not file.exists():
        console.print(f"[red]File not found: {file}[/red]")
        raise typer.Exit(1)

    console.print(f"[dim]Analyzing {file.name}...[/dim]")

    pipeline = IngestPipeline(use_stems=False)

    with console.status("Transcribing audio..."):
        result = pipeline.process_track(file, write_file_tags=False)

    # Display results in a nice table
    console.print()
    console.print(f"[bold cyan]📀 {result.title}[/bold cyan]")
    console.print()

    # Metadata table
    table = Table(show_header=False, box=None)
    table.add_column("Field", style="bold")
    table.add_column("Value")

    table.add_row("Language", result.language)
    table.add_row("Moods", ", ".join(result.moods) if result.moods else "[dim]none[/dim]")
    table.add_row("Themes", ", ".join(result.themes) if result.themes else "[dim]none[/dim]")
    table.add_row("Imagery", ", ".join(result.imagery) if result.imagery else "[dim]none[/dim]")

    console.print(table)

    if result.narrative:
        console.print()
        console.print("[bold]Narrative:[/bold]")
        console.print(f"  {result.narrative}")

    # Show lyrics preview
    if result.lyrics:
        console.print()
        console.print("[bold]Lyrics Preview:[/bold]")
        preview = result.lyrics[:500] + "..." if len(result.lyrics) > 500 else result.lyrics
        console.print(f"[dim]{preview}[/dim]")


@app.command()
def search(
    query: str = typer.Argument(..., help="Natural language search query"),
    limit: int = typer.Option(5, "--limit", "-n", help="Number of results"),
    mode: str = typer.Option("hybrid", "--mode", "-m", help="Search mode: hybrid, lyrics, or audio"),
):
    """
    Search music by vibe/description.

    Examples:
        vectrola search "melancholic songs about heartbreak"
        vectrola search "upbeat Hindi party songs"
        vectrola search "romantic duets from 90s Bollywood"
        vectrola search "dark ambient texture" --mode audio
    """
    from vectrola.search.semantic import SemanticSearch

    # Check Qdrant is running
    try:
        from vectrola.storage.qdrant import get_db
        db = get_db()
        count = db.count()
    except Exception as e:
        console.print("[red]Error: Cannot connect to Qdrant.[/red]")
        console.print("[dim]Start it with: docker run -d -p 6333:6333 qdrant/qdrant[/dim]")
        raise typer.Exit(1)

    if count == 0:
        console.print("[yellow]No tracks indexed yet. Run 'vectrola ingest' first.[/yellow]")
        raise typer.Exit(1)

    mode_label = {"hybrid": "hybrid (lyrics + audio)", "lyrics": "lyrics only", "audio": "audio only"}
    console.print(f"[dim]Searching {count} tracks... [{mode_label.get(mode, mode)}][/dim]")

    searcher = SemanticSearch()
    results = searcher.search(query, limit=limit, mode=mode)

    if not results:
        console.print("[yellow]No matching tracks found.[/yellow]")
        raise typer.Exit(0)

    console.print()
    console.print(f"[bold]Results for:[/bold] {query}")
    console.print()

    for i, r in enumerate(results, 1):
        artist_str = ", ".join(r.artists) if r.artists else "Unknown"
        console.print(f"[cyan]{i}. {artist_str} - {r.title}[/cyan] [dim](score: {r.score:.2f})[/dim]")

        if r.movie and r.movie != r.album:
            console.print(f"   [dim]Movie: {r.movie}[/dim]")

        if r.moods:
            console.print(f"   Moods: {', '.join(r.moods)}")

        if r.themes:
            console.print(f"   Themes: {', '.join(r.themes)}")

        console.print()


@app.command()
def similar(
    track_name: str = typer.Argument(..., help="Track name or file path"),
    limit: int = typer.Option(5, "--limit", "-n", help="Number of results"),
    mode: str = typer.Option("audio", "--mode", "-m", help="Similarity mode: audio (acoustic) or lyrics"),
):
    """
    Find tracks similar to a given track.

    Acoustic similarity (default) finds tracks that sound similar.
    Lyrics similarity finds tracks with similar themes/moods.

    Examples:
        vectrola similar "Tum Hi Ho"
        vectrola similar "Ae Dil Hai Mushkil" --mode lyrics
        vectrola similar /path/to/song.mp3
    """
    from vectrola.search.semantic import SemanticSearch
    from vectrola.storage.qdrant import get_db

    # Check if it's a file path
    track_path = Path(track_name)
    if not track_path.exists():
        # Search for track by name
        db = get_db()
        tracks = db.list_all(limit=500)

        # Find matching track
        matching = None
        for t in tracks:
            title = t.payload.get("title", "").lower()
            if track_name.lower() in title:
                matching = t.payload.get("file_path")
                console.print(f"[dim]Found: {t.payload.get('title')}[/dim]")
                break

        if not matching:
            console.print(f"[red]Track not found: {track_name}[/red]")
            console.print("[dim]Tip: Use full path or exact title[/dim]")
            raise typer.Exit(1)

        track_path = Path(matching)

    mode_label = "acoustic" if mode == "audio" else "lyrical"
    console.print(f"[dim]Finding {mode_label} similarity...[/dim]")

    searcher = SemanticSearch()
    results = searcher.find_similar(str(track_path), limit=limit, mode=mode)

    if not results:
        console.print("[yellow]No similar tracks found.[/yellow]")
        if mode == "audio":
            console.print("[dim]Make sure tracks have audio embeddings (run scripts/add_audio_embeddings.py)[/dim]")
        raise typer.Exit(0)

    console.print()
    console.print(f"[bold]Tracks similar to:[/bold] {track_path.stem}")
    console.print()

    for i, r in enumerate(results, 1):
        artist_str = ", ".join(r.artists) if r.artists else "Unknown"
        console.print(f"[cyan]{i}. {artist_str} - {r.title}[/cyan] [dim](similarity: {r.score:.2f})[/dim]")

        if r.moods:
            console.print(f"   Moods: {', '.join(r.moods)}")

        console.print()


@app.command()
def wiki(
    output: Path = typer.Option(Path("./wiki"), "--output", "-o", help="Wiki output directory"),
):
    """
    Generate Obsidian wiki from indexed tracks.

    Creates markdown pages with wikilinks for tracks, artists, moods, themes, and movies.
    Open the generated directory in Obsidian to explore the music knowledge graph.
    """
    from vectrola.storage.wiki import WikiGenerator

    # Check if there are indexed tracks
    try:
        from vectrola.storage.qdrant import get_db
        db = get_db()
        count = db.count()
    except Exception as e:
        console.print("[red]Error: Cannot connect to Qdrant.[/red]")
        console.print("[dim]Start it with: docker run -d -p 6333:6333 qdrant/qdrant[/dim]")
        raise typer.Exit(1)

    if count == 0:
        console.print("[yellow]No tracks indexed yet. Run 'vectrola ingest' first.[/yellow]")
        raise typer.Exit(1)

    # Generate wiki
    generator = WikiGenerator(output)
    generator.generate_all()

    console.print()
    console.print(f"[green]✅ Wiki generated at: {output}[/green]")
    console.print()
    console.print("[dim]To view in Obsidian:[/dim]")
    console.print(f"[dim]1. Open Obsidian[/dim]")
    console.print(f"[dim]2. Open folder as vault: {output.absolute()}[/dim]")
    console.print(f"[dim]3. Enable Graph View (Cmd+G) to see connections[/dim]")


@app.command()
def status():
    """Show Vectrola system status and component availability."""
    console.print("[bold]🎧 Vectrola Status[/bold]\n")

    checks = []

    # Check Whisper
    try:
        from faster_whisper import WhisperModel

        checks.append(("faster-whisper", "✓", "green"))
    except ImportError:
        checks.append(("faster-whisper", "✗ not installed", "red"))

    # Check Ollama
    try:
        import ollama

        # Try to connect
        try:
            ollama.list()
            checks.append(("Ollama", "✓ connected", "green"))
        except Exception:
            checks.append(("Ollama", "✗ not running (start with 'ollama serve')", "yellow"))
    except ImportError:
        checks.append(("Ollama", "✗ not installed", "red"))

    # Check mutagen
    try:
        import mutagen

        checks.append(("mutagen", "✓", "green"))
    except ImportError:
        checks.append(("mutagen", "✗ not installed", "red"))

    # Check Qdrant (Day 2)
    try:
        from qdrant_client import QdrantClient

        try:
            client = QdrantClient(url="http://localhost:6333", timeout=2)
            client.get_collections()
            checks.append(("Qdrant", "✓ connected", "green"))
        except Exception:
            checks.append(("Qdrant", "○ not running (Day 2)", "dim"))
    except ImportError:
        checks.append(("Qdrant", "○ not installed (Day 2)", "dim"))

    # Check sentence-transformers (Day 2)
    try:
        from sentence_transformers import SentenceTransformer

        checks.append(("sentence-transformers", "✓", "green"))
    except ImportError:
        checks.append(("sentence-transformers", "○ not installed (Day 2)", "dim"))

    # Check CLAP (Day 3)
    try:
        from transformers import ClapModel

        checks.append(("CLAP (transformers)", "✓", "green"))
    except ImportError:
        checks.append(("CLAP (transformers)", "○ not installed (Day 3)", "dim"))

    # Display
    table = Table(show_header=True, header_style="bold")
    table.add_column("Component")
    table.add_column("Status")

    for name, status, color in checks:
        table.add_row(name, f"[{color}]{status}[/{color}]")

    console.print(table)


def main():
    """Entry point for the CLI."""
    app()


if __name__ == "__main__":
    main()
