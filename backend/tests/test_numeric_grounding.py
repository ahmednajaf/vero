import pytest
from app.knowledge.contracts import ResearchOutput
from app.knowledge.provider import ResearchError
from app.knowledge.research import number_tokens, validate_claims


@pytest.mark.parametrize(
    "quote,claim",
    [
        ("Scope 1\n55,200\nFY2024", "Scope 1, 55200 tonnes in 2024."),
        (
            "Renewable electricity was 42% in 2024",
            "Renewable electricity was 42 percent in 2024.",
        ),
        ("In 2024 the change was −4.0%", "The change was -4% in 2024."),
        ("Scope 1 and 2 are stated separately", "Separate Scope 1, and Scope 2."),
    ],
)
def test_formatting_is_not_an_unsupported_number(quote, claim):
    output = ResearchOutput.model_validate(
        {
            "status": "answered",
            "claims": [
                {"text": claim, "citations": [{"evidence_id": "e", "quote": quote}]}
            ],
        }
    )
    assert validate_claims(output, [{"evidence_id": "e", "text": quote}])


@pytest.mark.parametrize(
    "quote,claim",
    [
        ("The value is 42%", "The value is 0.42."),
        ("The change is -4%", "The change is 4%."),
        ("The value is 420", "The value is 42%."),
        ("The value is 1,234", "The value is 1.234."),
        ("The report states FY24", "The year is 2024."),
    ],
)
def test_formatting_never_invents_conversion_or_sign(quote, claim):
    output = ResearchOutput.model_validate(
        {
            "status": "answered",
            "claims": [
                {"text": claim, "citations": [{"evidence_id": "e", "quote": quote}]}
            ],
        }
    )
    with pytest.raises(ResearchError, match="unsupported_number"):
        validate_claims(output, [{"evidence_id": "e", "text": quote}])


def test_trailing_punctuation_does_not_become_part_of_a_number():
    assert number_tokens("Scope 1, Scope 2. FY2024; 55,200.0 and 42 %.") == {
        "1",
        "2",
        "2024",
        "55200",
        "42%",
    }


@pytest.mark.parametrize(
    "text,claim,accepted",
    [
        (
            "Scope 1 and 2 emissions\n100 tonnes",
            "Scope 2 emissions are 100 tonnes (page 82).",
            True,
        ),
        (
            "Scopes 1, 2 and 3\n100 tonnes",
            "Scope 3 emissions are 100 tonnes (p. 82).",
            True,
        ),
        ("Scope 1\n100 tonnes", "Scope 3 emissions are 100 tonnes.", False),
        ("Scope 1\n100 tonnes", "Scope 1 emissions are 100 tonnes (page 83).", False),
        ("Scope 1\n100 tonnes", "Scope 1 emissions are 82 tonnes.", False),
        ("Scope 1\n100 tonnes", "Scope 1 emissions are 0.1 tonnes.", False),
    ],
)
def test_scope_headers_and_page_locators_are_checked_separately(text, claim, accepted):
    output = ResearchOutput.model_validate(
        {
            "status": "answered",
            "claims": [
                {
                    "text": claim,
                    "citations": [{"evidence_id": "e", "quote": "100 tonnes"}],
                }
            ],
        }
    )
    sources = [{"evidence_id": "e", "text": text, "page": 82}]
    if accepted:
        assert validate_claims(output, sources)
    else:
        with pytest.raises(ResearchError, match="unsupported_number"):
            validate_claims(output, sources)


def test_quantity_cannot_legitimise_wrong_page_or_scope():
    for claim in ("Scope 3 emissions are 3 tonnes.", "The value is 3 tonnes (page 3)."):
        output = ResearchOutput.model_validate(
            {
                "status": "answered",
                "claims": [
                    {
                        "text": claim,
                        "citations": [
                            {"evidence_id": "e", "quote": "Scope 1: 3 tonnes"}
                        ],
                    }
                ],
            }
        )
        with pytest.raises(ResearchError, match="unsupported_number"):
            validate_claims(
                output, [{"evidence_id": "e", "text": "Scope 1: 3 tonnes", "page": 82}]
            )
