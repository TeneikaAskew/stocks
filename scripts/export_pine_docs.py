#!/usr/bin/env python3
"""
Pine Script v6 User Manual Exporter
====================================
Scrapes the full TradingView Pine Script v6 docs and compiles into a single
searchable markdown file.

Usage:
    pip install requests beautifulsoup4 markdownify
    python export_pine_docs.py

Output: pine_script_v6_manual.md (in the current directory)
"""

import requests
import time
import re
import sys
from pathlib import Path

try:
    from bs4 import BeautifulSoup
    from markdownify import markdownify as md
except ImportError:
    print("Missing dependencies. Run:")
    print("  pip install requests beautifulsoup4 markdownify")
    sys.exit(1)

BASE = "https://www.tradingview.com/pine-script-docs"

# Complete table of contents - all 71 pages
PAGES = [
    ("Welcome to Pine Script v6", "/welcome"),
    ("Primer: First Steps", "/primer/first-steps"),
    ("Primer: First Indicator", "/primer/first-indicator"),
    ("Primer: Next Steps", "/primer/next-steps"),
    ("Language: Execution Model", "/language/execution-model"),
    ("Language: Type System", "/language/type-system"),
    ("Language: Script Structure", "/language/script-structure"),
    ("Language: Identifiers", "/language/identifiers"),
    ("Language: Variable Declarations", "/language/variable-declarations"),
    ("Language: Operators", "/language/operators"),
    ("Language: Conditional Structures", "/language/conditional-structures"),
    ("Language: Loops", "/language/loops"),
    ("Language: Built-ins", "/language/built-ins"),
    ("Language: User-defined Functions", "/language/user-defined-functions"),
    ("Language: Objects", "/language/objects"),
    ("Language: Enums", "/language/enums"),
    ("Language: Methods", "/language/methods"),
    ("Language: Arrays", "/language/arrays"),
    ("Language: Matrices", "/language/matrices"),
    ("Language: Maps", "/language/maps"),
    ("Visuals: Overview", "/visuals/overview"),
    ("Visuals: Backgrounds", "/visuals/backgrounds"),
    ("Visuals: Bar Coloring", "/visuals/bar-coloring"),
    ("Visuals: Bar Plotting", "/visuals/bar-plotting"),
    ("Visuals: Colors", "/visuals/colors"),
    ("Visuals: Fills", "/visuals/fills"),
    ("Visuals: Levels", "/visuals/levels"),
    ("Visuals: Lines and Boxes", "/visuals/lines-and-boxes"),
    ("Visuals: Plots", "/visuals/plots"),
    ("Visuals: Tables", "/visuals/tables"),
    ("Visuals: Text and Shapes", "/visuals/text-and-shapes"),
    ("Concepts: Alerts", "/concepts/alerts"),
    ("Concepts: Bar States", "/concepts/bar-states"),
    ("Concepts: Chart Information", "/concepts/chart-information"),
    ("Concepts: Inputs", "/concepts/inputs"),
    ("Concepts: Libraries", "/concepts/libraries"),
    ("Concepts: Non-standard Charts Data", "/concepts/non-standard-charts-data"),
    ("Concepts: Other Timeframes and Data", "/concepts/other-timeframes-and-data"),
    ("Concepts: Repainting", "/concepts/repainting"),
    ("Concepts: Sessions", "/concepts/sessions"),
    ("Concepts: Strategies", "/concepts/strategies"),
    ("Concepts: Strings", "/concepts/strings"),
    ("Concepts: Time", "/concepts/time"),
    ("Concepts: Timeframes", "/concepts/timeframes"),
    ("Writing: Style Guide", "/writing/style-guide"),
    ("Writing: Debugging", "/writing/debugging"),
    ("Writing: Profiling and Optimization", "/writing/profiling-and-optimization"),
    ("Writing: Publishing Scripts", "/writing/publishing"),
    ("Writing: Limitations", "/writing/limitations"),
    ("FAQ: General", "/faq/general"),
    ("FAQ: Alerts", "/faq/alerts"),
    ("FAQ: Data Structures", "/faq/data-structures"),
    ("FAQ: Functions", "/faq/functions"),
    ("FAQ: Indicators", "/faq/indicators"),
    ("FAQ: Other Data and Timeframes", "/faq/other-data-and-timeframes"),
    ("FAQ: Programming", "/faq/programming"),
    ("FAQ: Strategies", "/faq/strategies"),
    ("FAQ: Strings and Formatting", "/faq/strings-and-formatting"),
    ("FAQ: Techniques", "/faq/techniques"),
    ("FAQ: Times, Dates, and Sessions", "/faq/times-dates-and-sessions"),
    ("FAQ: Variables and Operators", "/faq/variables-and-operators"),
    ("FAQ: Visuals", "/faq/visuals"),
    ("Error Messages", "/error-messages"),
    ("Release Notes", "/release-notes"),
    ("Migration: Overview", "/migration-guides/overview"),
    ("Migration: To Pine Script v6", "/migration-guides/to-pine-version-6"),
    ("Migration: To Pine Script v5", "/migration-guides/to-pine-version-5"),
    ("Migration: To Pine Script v4", "/migration-guides/to-pine-version-4"),
    ("Migration: To Pine Script v3", "/migration-guides/to-pine-version-3"),
    ("Migration: To Pine Script v2", "/migration-guides/to-pine-version-2"),
    ("Where Can I Get More Information?", "/where-can-i-get-more-information"),
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
}


def extract_content(html: str) -> str:
    """Extract main article content, strip nav/sidebar, convert to markdown."""
    soup = BeautifulSoup(html, "html.parser")

    # TradingView docs use <article> or <main> for content
    content = soup.find("article") or soup.find("main") or soup.find("body")
    if not content:
        return ""

    # Remove nav, sidebar, footer, ToC, breadcrumbs
    for tag in content.find_all(["nav", "aside", "footer", "header"]):
        tag.decompose()
    for cls in [
        "sidebar", "nav", "navigation", "toc", "table-of-contents",
        "page-nav", "breadcrumb", "footer", "on-this-page",
    ]:
        for el in content.find_all(class_=re.compile(cls, re.I)):
            el.decompose()

    # Remove duplicate sidebar/nav link lists (the docs render the full TOC
    # in the page HTML even though it's hidden via CSS)
    for ul in content.find_all("ul"):
        links = ul.find_all("a", href=re.compile(r"/pine-script-docs/"))
        if len(links) > 10:
            ul.decompose()

    markdown_text = md(
        str(content),
        heading_style="ATX",
        code_language="pinescript",
        strip=["img"],  # strip images (they won't render in markdown anyway)
    )

    # Clean up
    markdown_text = re.sub(r"\n{4,}", "\n\n\n", markdown_text)
    markdown_text = re.sub(r"[ \t]+\n", "\n", markdown_text)
    # Remove lines that are just repeated nav links
    lines = markdown_text.split("\n")
    cleaned = []
    for line in lines:
        stripped = line.strip()
        # Skip lines that look like nav menu items
        if stripped.startswith("[") and "/pine-script-docs/" in stripped and len(stripped) < 200:
            continue
        cleaned.append(line)
    markdown_text = "\n".join(cleaned)

    return markdown_text.strip()


def main():
    output_parts = []

    # Header
    output_parts.append("# Pine Script v6 User Manual\n\n")
    output_parts.append(f"**Source:** {BASE}/\n\n")
    output_parts.append(f"**Exported:** {time.strftime('%Y-%m-%d %H:%M')}\n\n")
    output_parts.append("**Copyright:** TradingView, Inc.\n\n")
    output_parts.append("---\n\n")

    # Table of Contents
    output_parts.append("## Table of Contents\n\n")
    current_section = ""
    for title, path in PAGES:
        section = title.split(":")[0].strip() if ":" in title else title
        if section != current_section:
            current_section = section
            output_parts.append(f"\n**{section}**\n\n")
        output_parts.append(f"- {title}\n")
    output_parts.append("\n---\n\n")

    total = len(PAGES)
    session = requests.Session()
    session.headers.update(HEADERS)
    success = 0
    errors = 0

    for i, (title, path) in enumerate(PAGES):
        url = BASE + path
        pct = int((i / total) * 100)
        print(f"[{i+1:2d}/{total}] ({pct:3d}%) {title}...", end=" ", flush=True)

        try:
            resp = session.get(url, timeout=30)
            resp.raise_for_status()
            content = extract_content(resp.text)

            if content and len(content) > 100:
                output_parts.append(f"\n\n{'=' * 80}\n\n")
                output_parts.append(f"# {title}\n\n")
                output_parts.append(f"*Source: {url}*\n\n")
                output_parts.append(content)
                output_parts.append("\n")
                success += 1
                print(f"OK ({len(content):,} chars)")
            else:
                output_parts.append(f"\n\n# {title}\n\n")
                output_parts.append(f"*Source: {url}*\n\n")
                output_parts.append("*Content could not be extracted.*\n")
                errors += 1
                print("WARN: minimal content")

        except Exception as e:
            output_parts.append(f"\n\n# {title}\n\n")
            output_parts.append(f"*Source: {url}*\n\n")
            output_parts.append(f"*Error: {e}*\n")
            errors += 1
            print(f"ERROR: {e}")

        # Rate limit: ~1 req/sec
        time.sleep(1.0)

    # Write output
    out_path = Path("pine_script_v6_manual.md")
    full_text = "".join(output_parts)
    out_path.write_text(full_text, encoding="utf-8")

    print(f"\n{'=' * 60}")
    print(f"Done! {success}/{total} pages exported successfully ({errors} errors)")
    print(f"Output: {out_path.resolve()}")
    print(f"Size:   {len(full_text):,} characters ({len(full_text)//1024:,} KB)")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
