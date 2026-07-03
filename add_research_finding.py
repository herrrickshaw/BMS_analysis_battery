#!/usr/bin/env python3
"""
Interactive Script: Add New Research Findings
==============================================
Use this to add new findings to your research and regenerate all publication outputs.

Example usage:
    python3 add_research_finding.py

This will prompt you for finding details and automatically:
1. Add the finding to your research database
2. Regenerate all export files (BibTeX, Zotero, manuscript, etc.)
3. Update summary reports
"""

import json
import sys
from pathlib import Path
from datetime import datetime
from typing import Optional, List
import subprocess

# Import the toolkit
sys.path.insert(0, str(Path(__file__).parent))
from research_publishing_toolkit import (
    Finding, Reference, Dataset, Manuscript, ResearchPublishingToolkit
)


def prompt_for_finding() -> Finding:
    """Interactive prompt for new research finding"""
    print("\n" + "="*70)
    print("ADD NEW RESEARCH FINDING")
    print("="*70 + "\n")

    # Required fields
    title = input("📌 Finding Title (e.g., 'Model X improves accuracy by Y%'): ").strip()
    if not title:
        print("❌ Title required")
        return None

    description = input("\n📝 Description (1-3 sentences): ").strip()
    if not description:
        print("❌ Description required")
        return None

    # Impact level
    print("\n📊 Impact Level:")
    print("  1. HIGH   - Major contribution to research")
    print("  2. MEDIUM - Important but secondary")
    print("  3. LOW    - Nice to have, supporting detail")
    impact_choice = input("Select (1-3): ").strip()
    impact_map = {"1": "HIGH", "2": "MEDIUM", "3": "LOW"}
    impact = impact_map.get(impact_choice, "MEDIUM")

    # Status
    print("\n✅ Status:")
    print("  1. DOCUMENTED       - Described, needs validation")
    print("  2. VALIDATED        - Validated with data")
    print("  3. READY FOR PUBLICATION - Ready to share")
    status_choice = input("Select (1-3): ").strip()
    status_map = {"1": "DOCUMENTED", "2": "VALIDATED", "3": "READY FOR PUBLICATION"}
    status = status_map.get(status_choice, "DOCUMENTED")

    # Optional fields
    methodology = input("\n🔬 Methodology (optional, press Enter to skip): ").strip() or None
    paper_section = input("📄 Manuscript Section (default: 'findings'): ").strip() or "findings"

    # Metrics (JSON format)
    metrics_input = input("\n📈 Metrics as JSON (e.g., {\"accuracy\": \"0.92\", \"f1\": \"0.85\"}, or press Enter): ").strip()
    metrics = None
    if metrics_input:
        try:
            metrics = json.loads(metrics_input)
        except json.JSONDecodeError:
            print("⚠️  Invalid JSON, skipping metrics")

    # Tags
    tags_input = input("\n🏷️  Tags (comma-separated, e.g., 'machine-learning, backtesting'): ").strip()
    tags = [t.strip() for t in tags_input.split(",")] if tags_input else []

    publication_ready = status == "READY FOR PUBLICATION"

    finding = Finding(
        title=title,
        description=description,
        impact=impact,
        status=status,
        methodology=methodology,
        metrics=metrics,
        paper_section=paper_section,
        tags=tags,
        publication_ready=publication_ready,
        date_discovered=datetime.now().isoformat()
    )

    return finding


def prompt_for_reference() -> Optional[Reference]:
    """Interactive prompt for new reference"""
    print("\n" + "="*70)
    print("ADD NEW REFERENCE (optional)")
    print("="*70)
    print("Skip this if not adding a reference (press Enter when asked for title)\n")

    title = input("📚 Reference Title (or press Enter to skip): ").strip()
    if not title:
        return None

    authors_input = input("✍️  Authors (comma-separated, e.g., 'Smith, J., Jones, K.'): ").strip()
    authors = [a.strip() for a in authors_input.split(",")] if authors_input else ["Unknown"]

    year_input = input("📅 Year (e.g., 2021): ").strip()
    try:
        year = int(year_input)
    except ValueError:
        year = datetime.now().year

    source = input("🔗 Source (academic/industry/proprietary/internal, default: 'industry'): ").strip() or "industry"
    url = input("🌐 URL (optional): ").strip() or None
    journal = input("📰 Journal Name (optional): ").strip() or None
    notes = input("💬 Notes (optional): ").strip() or None

    ref = Reference(
        title=title,
        authors=authors,
        year=year,
        source=source,
        url=url,
        journal=journal,
        notes=notes
    )

    return ref


def save_findings_to_json(findings: List[Finding], path: Path):
    """Save findings to JSON for persistence"""
    data = {
        "findings": [
            {
                "title": f.title,
                "description": f.description,
                "impact": f.impact,
                "status": f.status,
                "methodology": f.methodology,
                "metrics": f.metrics,
                "paper_section": f.paper_section,
                "tags": f.tags,
                "publication_ready": f.publication_ready,
                "date_discovered": f.date_discovered
            }
            for f in findings
        ],
        "last_updated": datetime.now().isoformat()
    }
    path.write_text(json.dumps(data, indent=2))
    print(f"✓ Findings saved to {path}")


def load_findings_from_json(path: Path) -> List[Finding]:
    """Load previously saved findings"""
    if not path.exists():
        return []

    data = json.loads(path.read_text())
    findings = []
    for f in data.get("findings", []):
        finding = Finding(
            title=f["title"],
            description=f["description"],
            impact=f["impact"],
            status=f["status"],
            methodology=f.get("methodology"),
            metrics=f.get("metrics"),
            paper_section=f.get("paper_section", "findings"),
            tags=f.get("tags", []),
            publication_ready=f.get("publication_ready", False),
            date_discovered=f.get("date_discovered")
        )
        findings.append(finding)
    return findings


def main():
    """Main workflow"""
    output_dir = Path("/Users/umashankar/research_outputs")
    output_dir.mkdir(exist_ok=True)

    findings_db_path = output_dir / "findings_database.json"

    print("""
╔════════════════════════════════════════════════════════════════════╗
║  Research Publishing Toolkit - Add Findings                       ║
║                                                                    ║
║  This tool lets you add new findings to your research and         ║
║  automatically regenerate all publication outputs.                ║
╚════════════════════════════════════════════════════════════════════╝
""")

    # Load existing findings
    existing_findings = load_findings_from_json(findings_db_path)
    print(f"📊 Loaded {len(existing_findings)} existing findings\n")

    # Prompt for new finding
    new_finding = prompt_for_finding()
    if not new_finding:
        print("❌ Finding not added")
        return

    # Prompt for reference
    new_ref = prompt_for_reference()

    # Confirm
    print("\n" + "="*70)
    print("CONFIRM & REGENERATE")
    print("="*70)
    print(f"\nAdding finding: {new_finding.title}")
    print(f"Impact: {new_finding.impact}")
    print(f"Status: {new_finding.status}")
    if new_ref:
        print(f"\nAlso adding reference: {new_ref.title}")

    confirm = input("\n✓ Regenerate all outputs? (y/n): ").strip().lower()
    if confirm != "y":
        print("❌ Cancelled")
        return

    # Reinitialize toolkit with all findings
    print("\n🔄 Regenerating outputs...")

    toolkit = ResearchPublishingToolkit(str(Path("/Users/umashankar/Downloads/code/python_files")))

    # Add existing findings
    for f in existing_findings:
        toolkit.add_finding(f)

    # Add new finding
    toolkit.add_finding(new_finding)

    # Add base references
    toolkit.add_reference(Reference(
        title="A Disciplined Approach to Global Allocation",
        authors=["Arnott, Robert D.", "Beck, Shashin L."],
        year=2015,
        source="academic",
        journal="Research Affiliates Publications"
    ))
    toolkit.add_reference(Reference(
        title="Free Cash Flow to Equity Model",
        authors=["Damodaran, Aswath"],
        year=2012,
        source="academic",
        journal="Journal of Applied Corporate Finance",
        doi="10.1111/j.1745-6622.2012.00060.x"
    ))
    toolkit.add_reference(Reference(
        title="Machine Learning in Finance: A Literature Review",
        authors=["Jiang, Wenhao"],
        year=2021,
        source="academic",
        journal="Quantitative Finance",
        doi="10.1080/14697688.2021.1915942",
        url="https://arxiv.org/abs/2101.01176"
    ))
    toolkit.add_reference(Reference(
        title="The Intelligent Investor: The Definitive Book on Value Investing",
        authors=["Graham, Benjamin"],
        year=1949,
        source="industry"
    ))

    # Add new reference if provided
    if new_ref:
        toolkit.add_reference(new_ref)

    # Add datasets
    toolkit.add_dataset(Dataset(
        name="Quarterly Financial Data (2021-2026)",
        description="Quarterly revenue, capex, debt, FCF, ROIC for 60 companies",
        size="60 companies",
        time_period="5 years (2021-2026)",
        source="SEC EDGAR, NSE, BSE, Yahoo Finance",
        records=1160,
        metrics_extracted=["Revenue", "CapEx", "Debt", "FCF", "ROIC"],
        quality_score=0.97
    ))

    # Create manuscript
    manuscript = Manuscript(
        title="Global Expansion Stock Screening: An 11-Dimensional Model for Predicting Outperformance",
        abstract="Enhanced stock screening model with ROIC, DSC, and Asset Turnover dimensions. 11-D model outperforms baseline by 0.06+ F1 score.",
        authors=["Uma Shankar"],
        institution="Independent Research",
        target_journal="Journal of Financial Research",
        findings=toolkit.findings,
        references=toolkit.references,
        datasets=toolkit.datasets
    )
    toolkit.create_manuscript(manuscript)

    # Export all formats
    print("\n✓ Exporting BibTeX...")
    toolkit.export_bibtex(output_dir / "references.bib")

    print("✓ Exporting RIS for Zotero...")
    toolkit.export_ris(output_dir / "references.ris")

    print("✓ Exporting data dictionary...")
    toolkit.export_data_dictionary(output_dir / "appendix_data_dictionary.md")

    print("✓ Exporting manuscript outline...")
    toolkit.export_manuscript_outline(0, output_dir / "manuscript_outline.md")

    print("✓ Exporting LaTeX template...")
    toolkit.export_manuscript_latex(0, output_dir / "manuscript.tex")

    print("✓ Exporting research graph metadata...")
    toolkit.export_research_graph_metadata(output_dir / "research_graph.json")

    print("✓ Exporting Consensus queries...")
    toolkit.export_consensus_queries(output_dir / "consensus_queries.md")

    print("✓ Generating publishing workflow...")
    toolkit.generate_publishing_workflow(output_dir / "PUBLISHING_WORKFLOW.md")

    print("✓ Generating summary report...")
    toolkit.generate_summary_report(output_dir / "RESEARCH_SUMMARY.md")

    # Save findings to JSON
    all_findings = existing_findings + [new_finding]
    save_findings_to_json(all_findings, findings_db_path)

    print("\n" + "="*70)
    print("✅ ALL OUTPUTS REGENERATED")
    print("="*70)
    print(f"\n📊 Research Status:")
    print(f"   Total Findings: {len(all_findings)}")
    print(f"   Publication-Ready: {len([f for f in all_findings if f.publication_ready])}")
    print(f"   Total References: {len(toolkit.references)}")
    print(f"\n📁 Outputs updated in: {output_dir}")
    print("\n✨ Next steps:")
    print("   1. Review updated manuscript_outline.md")
    print("   2. Import updated references.ris to Zotero")
    print("   3. Update manuscript.tex in Overleaf")
    print("   4. Continue writing!")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n❌ Cancelled")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
