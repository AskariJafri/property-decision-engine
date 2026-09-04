"""Extraction is a draft for a human, not a source of facts."""

from typing import Any

import pytest

from app.ai.contracts import LlmUnavailableError
from app.ingestion.listing import extract, validate

LISTING = """
Charming detached home at 88 Marlow Avenue, Toronto.
Offered at 849000. 3 bedrooms, 2.5 bathrooms, approximately 1450 sq ft.
Built in 1998. Annual property taxes 4820. Two car parking.
Furnace original to the home. Sold as is where is.
"""


class FakeModel:
    def __init__(self, payload: dict[str, Any]):
        self.payload = payload

    @property
    def model_id(self) -> str:
        return "llama3.1:8b-instruct-q4_K_M"

    async def complete_json(self, **_: Any) -> dict[str, Any]:
        return self.payload


class TestValidation:
    def test_plausible_values_survive(self):
        result = validate({"listing_price": 849000, "bedrooms": 3, "square_feet": 1450})
        assert result.fields["listing_price"] == 849000
        assert not result.rejected

    def test_a_misplaced_decimal_is_rejected_not_repaired(self):
        """A price of 85 is dropped and reported. Multiplying it by ten thousand
        because that is probably what was meant is exactly the guessing we refuse."""
        result = validate({"listing_price": 85})
        assert "listing_price" not in result.fields
        assert "outside the plausible range" in result.rejected["listing_price"]

    def test_unknown_fields_are_refused(self):
        assert validate({"vibe": "cosy"}).rejected["vibe"]

    def test_money_converts_to_integer_cents(self):
        result = validate({"listing_price": 849000, "monthly_condo_fee": 612.5})
        assert result.as_cents() == {
            "listing_price_cents": 84_900_000,
            "monthly_condo_fee_cents": 61_250,
        }


class TestExtraction:
    async def test_a_faithful_extraction_is_anchored_in_the_text(self):
        model = FakeModel(
            {
                "address": "88 Marlow Avenue, Toronto",
                "listing_price": 849000,
                "bedrooms": 3,
                "square_feet": 1450,
                "year_built": 1998,
                "annual_property_tax": 4820,
            }
        )
        result = await extract(text=LISTING, provider=model)
        assert result.fields["listing_price"] == 849000
        assert "849000" in result.evidence["listing_price"]
        assert result.requires_confirmation is True
        assert result.model_id.startswith("llama3.1")

    async def test_a_number_absent_from_the_document_is_dropped(self):
        """The strongest available check on extraction: if the figure is not in the
        text, the model did not read it there."""
        result = await extract(
            text=LISTING, provider=FakeModel({"listing_price": 849000, "square_feet": 2400})
        )
        assert "square_feet" not in result.fields
        assert "does not appear in the document" in result.rejected["square_feet"]

    async def test_an_empty_document_is_refused(self):
        with pytest.raises(LlmUnavailableError, match="nothing to extract"):
            await extract(text="   ", provider=FakeModel({}))

    async def test_nothing_is_ever_returned_pre_confirmed(self):
        result = await extract(text=LISTING, provider=FakeModel({"bedrooms": 3}))
        assert result.requires_confirmation is True
