#!/usr/bin/env python3
import os
import subprocess
import sys
import re
import time
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.text import Text
from rich.live import Live

console = Console()

def get_banner():
    banner_text = """
    ███████╗██████╗ ███████╗███████╗    ███████╗██████╗  ██████╗ ███╗   ██╗████████╗██╗███████╗██████╗ 
    ██╔════╝██╔══██╗██╔════╝██╔════╝    ██╔════╝██╔══██╗██╔═══██╗████╗  ██║╚══██╔══╝██║██╔════╝██╔══██╗
    █████╗  ██████╔╝█████╗  █████╗      █████╗  ██████╔╝██║   ██║██╔██╗ ██║   ██║   ██║█████╗  ██████╔╝
    ██╔══╝  ██╔══██╗██╔══╝  ██╔══╝      ██╔══╝  ██╔══██╗██║   ██║██║╚██╗██║   ██║   ██║██╔══╝  ██╔══██╗
    ██║     ██║  ██║███████╗███████╗    ██║     ██║  ██║╚██████╔╝██║ ╚████║   ██║   ██║███████╗██║  ██║
    ╚═╝     ╚═╝  ╚═╝╚══════╝╚══════╝    ╚═╝     ╚═╝  ╚═╝ ╚═════╝ ╚═╝  ╚═══╝   ╚═╝   ╚═╝╚══════╝╚═╝  ╚═╝
                                        FREE FRONTIER v0.1
    """
    return Panel(Text(banner_text, style="bold cyan"), border_style="blue")

def main():
    root = Path(__file__).parent
    env_file = root / ".env"
    
    console.print(get_banner())
    
    # Load .env file
    try:
        from dotenv import load_dotenv
        if env_file.exists():
            load_dotenv(env_file)
            console.print(f"[bold green]✔[/bold green] Loaded environment from {env_file.name}")
    except ImportError:
        console.print("[yellow]⚠[/yellow] python-dotenv not found, skipping .env load")

    # Verify keys from config.yaml
    cfg = root / "config.yaml"
    if cfg.exists():
        required_vars = set(re.findall(r'os\.environ/([A-Z0-9_]+)', cfg.read_text()))
        
        table = Table(title="Environment Status", show_header=True, header_style="bold magenta")
        table.add_column("Variable", style="cyan")
        table.add_column("Status", justify="center")
        
        missing_count = 0
        for var in sorted(required_vars):
            if os.environ.get(var):
                table.add_row(var, "[bold green]OK[/bold green]")
            else:
                table.add_row(var, "[bold red]MISSING[/bold red]")
                missing_count += 1
        
        console.print(table)
        
        if missing_count > 0:
            console.print(f"\n[bold yellow]Warning:[/bold yellow] {missing_count} variable(s) are missing. Some models may be unavailable.\n")
        else:
            console.print("\n[bold green]Success:[/bold green] All providers configured.\n")

    # Prepare command environment
    clean_env = os.environ.copy()
    if "VIRTUAL_ENV" in clean_env:
        del clean_env["VIRTUAL_ENV"]
    
    # Crucial: Add current directory to PYTHONPATH so LiteLLM can find proxy_callbacks.py
    current_pythonpath = clean_env.get("PYTHONPATH", "")
    clean_env["PYTHONPATH"] = f".:{current_pythonpath}" if current_pythonpath else "."
    clean_env["PYTHONUNBUFFERED"] = "1"
    clean_env["LITELLM_LOG"] = "ERROR" # Silence common LiteLLM help messages

    # Define commands
    proxy_cmd = ["uv", "run", "--no-sync", "litellm", "--config", str(cfg), "--port", "4000"]
    monitor_cmd = ["uv", "run", "--no-sync", "python", "monitor.py"]
    
    console.print(f"[bold blue]Starting Orchestrator...[/bold blue]")
    
    processes = []
    try:
        # Open log file for proxy
        log_file = open("proxy.log", "a")
        
        # Start Proxy
        console.print(f" [bold cyan]>[/bold cyan] Launching LiteLLM Proxy on port 4000 (logs -> proxy.log)...")
        proxy_proc = subprocess.Popen(
            proxy_cmd, 
            env=clean_env,
            stdout=log_file,
            stderr=log_file
        )
        processes.append(proxy_proc)
        
        # Give the proxy a second to start
        time.sleep(2)
        
        # Start Monitor
        console.print(f" [bold green]>[/bold green] Launching Proactive Health Monitor...")
        monitor_proc = subprocess.Popen(monitor_cmd, env=clean_env)
        processes.append(monitor_proc)
        
        console.print("\n[bold green]✔[/bold green] Both systems running. Press Ctrl+C to stop.\n")
        
        # Wait for processes
        while True:
            if proxy_proc.poll() is not None:
                console.print("[red]Proxy process exited unexpectedy.[/red]")
                break
            if monitor_proc.poll() is not None:
                console.print("[yellow]Monitor process exited. Restarting in 5s...[/yellow]")
                time.sleep(5)
                monitor_proc = subprocess.Popen(monitor_cmd, env=clean_env)
                processes[1] = monitor_proc
            time.sleep(1)
            
    except KeyboardInterrupt:
        console.print("\n[bold yellow]Shutting down gracefully...[/bold yellow]")
        for p in processes:
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()
        console.print("[bold green]Shutdown complete.[/bold green]")
        sys.exit(0)

if __name__ == "__main__":
    main()
