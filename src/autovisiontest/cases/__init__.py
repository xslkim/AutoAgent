"""Test case schema — Pydantic models for test case definition and storage.

Models correspond to the product document §4.3:
- TestCase: Top-level test case with metadata, steps, and expectations
- AppConfig: Application configuration for the test
- Step: A single recorded step
- Expect: Expected state after a step
- CaseMetadata: Metadata about the test case (fingerprints, timestamps, etc.)
"""