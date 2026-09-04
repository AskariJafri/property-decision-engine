"""The no-model listing parser: exact matches, with the span they came from."""

from app.ingestion.deterministic import parse

TYPICAL = """
Welcome to 88 Marlow Avenue! Offered at $849,000.
3 bedrooms, 2.5 bathrooms, approximately 1,450 sq ft of living space.
Built in 1998 and lovingly maintained. Annual property taxes $4,820.
Two car parking. Furnace original to the home. Sold as is where is.
"""

CONDO = """
Stunning 2 bed, 2 bath suite. 910 sqft. Asking $625,000.
Maintenance fee $612.50 monthly includes heat and water. Built 2014.
"""


class TestTypicalListing:
    def test_it_reads_the_common_fields(self):
        result = parse(TYPICAL)
        assert result.fields["listing_price"] == 849000
        assert result.fields["bedrooms"] == 3
        assert result.fields["bathrooms"] == 2.5
        assert result.fields["square_feet"] == 1450
        assert result.fields["year_built"] == 1998
        assert result.fields["annual_property_tax"] == 4820

    def test_written_out_counts_are_not_dropped(self):
        """ "Two car parking" is ordinary listing English, and a digits-only pass
        loses it silently."""
        assert parse(TYPICAL).fields["parking_spaces"] == 2

    def test_every_value_carries_the_text_it_came_from(self):
        result = parse(TYPICAL)
        for field in result.fields:
            assert result.evidence[field], f"{field} has no evidence span"
        assert "849,000" in result.evidence["listing_price"]

    def test_it_needs_no_model(self):
        assert parse(TYPICAL).model_id == "deterministic:patterns"

    def test_nothing_is_returned_pre_confirmed(self):
        assert parse(TYPICAL).requires_confirmation is True


class TestCondoListing:
    def test_abbreviations_and_decimal_fees(self):
        result = parse(CONDO)
        assert result.fields["listing_price"] == 625000
        assert result.fields["bedrooms"] == 2
        assert result.fields["square_feet"] == 910
        assert result.fields["year_built"] == 2014
        # The cents matter: truncating this to $612 understates the fee every month.
        assert result.fields["monthly_condo_fee"] == 612.5
        assert result.as_cents()["monthly_condo_fee_cents"] == 61_250


class TestRefusals:
    def test_an_empty_document_yields_nothing_rather_than_defaults(self):
        result = parse("")
        assert result.fields == {}
        assert result.rejected == {}

    def test_prose_with_no_figures_yields_nothing(self):
        result = parse("A charming home in a wonderful neighbourhood. Must be seen!")
        assert "listing_price" not in result.fields

    def test_a_matched_but_implausible_price_is_rejected_with_a_reason(self):
        """The parser feeds the same validation as the model path, so a figure that
        matches the pattern but cannot be a house price is refused, not kept."""
        result = parse("Priced at $999 for a quick sale.")
        assert "listing_price" not in result.fields
        assert "outside the plausible range" in result.rejected["listing_price"]

    def test_a_figure_too_small_to_be_a_price_is_never_claimed_as_one(self):
        """ "$85" does not match the money pattern at all, so nothing is asserted
        and nothing is rejected — the user simply enters the price themselves."""
        result = parse("Priced at $85 for a quick sale.")
        assert result.fields == {} and result.rejected == {}


class TestRealListingLayouts:
    """The shapes real listings actually come in, rather than the tidy prose one."""

    def test_a_bare_price_with_no_keyword_is_still_found(self):
        """Listings lead with the price and often give it no label at all. Requiring
        a keyword meant the single most important field was the one most often
        missed."""
        result = parse("$899,900  3+1 Bed  2 Bath  1,450 sqft  Built 1998")
        assert result.fields["listing_price"] == 899900
        assert result.fields["bedrooms"] == 3  # "3+1" is three, plus a basement one

    def test_a_label_table_does_not_shift_every_field_by_one(self):
        """The bug this guards: a digit-first pattern reached back across the line
        break, took the trailing zero of the price as the bedroom count, and let
        bathrooms pick up the bedroom figure. Wrong, and confidently so."""
        result = parse(
            "Price: $1,299,000\nBedrooms: 4\nBathrooms: 3\n"
            "Approx Sq Ft: 2000\nTaxes: $7,240.00 / 2025"
        )
        assert result.fields["listing_price"] == 1_299_000
        assert result.fields["bedrooms"] == 4
        assert result.fields["bathrooms"] == 3
        assert result.fields["square_feet"] == 2000
        assert result.fields["annual_property_tax"] == 7240

    def test_pipe_separated_summaries_and_abbreviated_fees(self):
        result = parse("$749,900 | 2 Bed | 2 Bath | 940 SqFt | Maint. Fee $612.50")
        assert result.fields["listing_price"] == 749900
        assert result.fields["monthly_condo_fee"] == 612.5

    def test_a_reduced_price_takes_the_current_one(self):
        """ "Was $999,000, now $899,900" — the buyer pays the second figure."""
        result = parse("Was $999,000, now $899,900. 3 bed, 2 bath.")
        assert result.fields["listing_price"] == 899900

    def test_a_floor_area_is_never_mistaken_for_a_price(self):
        """The bare-price fallback requires a dollar sign precisely so that a
        four-digit floor area or a year cannot become the asking price."""
        result = parse("Spacious 1,450 sq ft home built in 1998. Three bedrooms.")
        assert "listing_price" not in result.fields
