"""
Risk Profiler Survey Bot - Main Application
Collects risk factor information across multiple domains
"""
import asyncio
import json
from pathlib import Path
from datetime import datetime
from dotenv import load_dotenv

from agents.domain1_agent import run_domain1_survey


async def main():
    """Main survey application"""
    print("\n" + "=" * 70)
    print(" " * 15 + "RISK PROFILER SURVEY BOT")
    print(" " * 10 + "Multi-Domain Risk Assessment System")
    print("=" * 70)
    print("\nThis survey will collect information across 7 domains to assess")
    print("risk factors for vulnerable populations.")
    print("\nCurrently available: Domain 1 - Demographics & Vulnerability Factors")
    print("=" * 70)
    print()

    # Run Domain 1 survey
    domain1_data = await run_domain1_survey()

    if domain1_data:
        # Display results
        print("\n" + "=" * 70)
        print("DOMAIN 1 ASSESSMENT COMPLETE")
        print("=" * 70)

        # Get risk summary
        summary = domain1_data.get_risk_summary()

        print("\n📊 RISK SUMMARY:")
        print("-" * 70)
        print(f"Total Children Under 5: {summary['total_children']}")
        print(f"High-Risk Age Children (6-23 months): {summary['high_risk_age_children']}")
        print(f"Children with Malnutrition Signs: {summary['malnourished_children']}")
        print(f"Single-Parent Household: {'Yes' if summary['single_parent_household'] else 'No'}")
        print(f"Vulnerable Members Present: {'Yes' if summary['vulnerable_members_present'] else 'No'}")
        print("-" * 70)
        print(f"Overall Vulnerability Score: {summary['overall_vulnerability_score']:.2f}")
        print(f"Domain Weight: {summary['domain_weight']:.0%}")
        print(f"Weighted Score: {summary['weighted_score']:.2f}")
        print("=" * 70)

        # Save results to file
        output_dir = Path("survey_results")
        output_dir.mkdir(exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        output_file = output_dir / f"domain1_survey_{timestamp}.json"

        output_data = {
            "timestamp": datetime.now().isoformat(),
            "domain": "Domain 1 - Demographics & Vulnerability Factors",
            "data": domain1_data.model_dump(),
            "summary": summary
        }

        with open(output_file, 'w') as f:
            json.dump(output_data, f, indent=2)

        print(f"\n✅ Survey results saved to: {output_file}")
        print()

        # Show individual child vulnerability scores
        if domain1_data.children:
            print("\n👶 INDIVIDUAL CHILD VULNERABILITY SCORES:")
            print("-" * 70)
            for i, child in enumerate(domain1_data.children, 1):
                print(f"Child {i}:")
                print(f"  Age: {child.age_months} months ({child.age_range.value})")
                print(f"  Malnutrition Signs: {'Yes' if child.has_malnutrition_signs else 'No'}")
                print(f"  Vulnerability Score: {child.vulnerability_score:.2f}")
                print()

    else:
        print("\n❌ Survey was not completed.")

    print("\n" + "=" * 70)
    print("Thank you for participating in the risk assessment survey!")
    print("=" * 70)


if __name__ == "__main__":
    # Load environment variables
    load_dotenv()

    # Run the main application
    asyncio.run(main())
