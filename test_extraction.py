"""Quick test to debug the extraction"""
import asyncio
from dotenv import load_dotenv
from agents.domain1_agent import get_extraction_agent
from models.domain1 import Domain1Data

load_dotenv()

async def test_extraction():
    # Sample conversation
    conversation = """
User: I have 2 children under 5
Agent: Thank you. Can you tell me the age of the first child in months?
User: The first child is 10 months old
Agent: Has this child shown any signs of malnutrition such as weight loss or growth problems?
User: Yes, the child has shown some weight loss
Agent: Thank you. Now, can you tell me the age of the second child in months?
User: The second child is 20 months old
Agent: Has the second child shown any signs of malnutrition?
User: No, the second child seems healthy
Agent: Are there any elderly household members?
User: Yes, my mother lives with us and she is 75
Agent: Are there any immunocompromised or chronically ill household members?
User: No immunocompromised members
Agent: Who is the primary caregiver for the children?
User: I'm a single mother
"""

    extraction_agent = get_extraction_agent()

    print("Testing extraction from conversation...")
    print("="*60)

    result = await extraction_agent.run(
        f"Extract the household demographic data from this conversation:\n\n{conversation}"
    )

    print("\nExtracted Data:")
    print("="*60)
    print(type(result.output))
    print(result.output)

    if isinstance(result.output, Domain1Data):
        print("\n✅ Successfully extracted Domain1Data!")
        print(f"Number of children: {result.output.num_children_under_5}")
        print(f"Children details: {result.output.children}")
        print(f"Elderly members: {result.output.has_elderly_members}")
        print(f"Primary caregiver: {result.output.primary_caregiver}")
    else:
        print(f"\n❌ Got unexpected type: {type(result.output)}")

if __name__ == "__main__":
    asyncio.run(test_extraction())
