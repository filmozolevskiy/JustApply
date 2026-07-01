from unittest.mock import MagicMock, patch

import pytest
from src.core import gemini_client


@pytest.mark.asyncio
async def test_generate_text_returns_stripped_response():
    mock_response = MagicMock()
    mock_response.text = "  hello world  "
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response

    with patch.object(gemini_client, "get_client", return_value=mock_client):
        result = await gemini_client.generate_text("test prompt")

    assert result == "hello world"
    mock_client.models.generate_content.assert_called_once_with(
        model=gemini_client.MODEL_NAME,
        contents="test prompt",
    )


@pytest.mark.asyncio
async def test_generate_text_raises_when_api_key_missing():
    with patch.object(gemini_client, "get_client", return_value=None):
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY not set"):
            await gemini_client.generate_text("test prompt")


@pytest.mark.asyncio
async def test_generate_text_from_pdf_sends_pdf_part_and_prompt():
    mock_response = MagicMock()
    mock_response.text = "# QA Profile\n\n**SUMMARY**\nConverted."
    mock_client = MagicMock()
    mock_client.models.generate_content.return_value = mock_response
    pdf_bytes = b"%PDF-1.4 fake"
    prompt = "Convert this resume to markdown."

    with patch.object(gemini_client, "get_client", return_value=mock_client):
        result = await gemini_client.generate_text_from_pdf(pdf_bytes, prompt)

    assert result.startswith("# QA Profile")
    call_kwargs = mock_client.models.generate_content.call_args.kwargs
    assert call_kwargs["model"] == gemini_client.MODEL_NAME
    contents = call_kwargs["contents"]
    assert len(contents) == 2
    assert contents[1] == prompt


@pytest.mark.asyncio
async def test_generate_text_from_pdf_raises_when_api_key_missing():
    with patch.object(gemini_client, "get_client", return_value=None):
        with pytest.raises(RuntimeError, match="GEMINI_API_KEY not set"):
            await gemini_client.generate_text_from_pdf(b"%PDF", "prompt")
