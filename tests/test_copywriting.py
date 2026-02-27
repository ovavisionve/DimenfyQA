from unittest.mock import MagicMock, patch

import pytest

from app.services.copywriting_service import CopywritingService


@pytest.fixture
def copywriting_service():
    with patch("app.services.copywriting_service.settings") as mock_settings:
        mock_settings.ANTHROPIC_API_KEY = "test-key"
        service = CopywritingService()
        return service


class TestCopywritingService:
    def test_generate_dm_returns_text(
        self, copywriting_service, sample_lead_data, sample_client_config
    ):
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text="Hey Test, vi que tienes una agencia de marketing y me llamo la atencion tu enfoque en growth. Nosotros ayudamos a agencias como la tuya a automatizar la generacion de leads con IA. Te interesaria saber como funciona?"
            )
        ]

        lead_data = {**sample_lead_data, "research_data": "Test Business is a marketing agency based in Miami."}

        with patch.object(
            copywriting_service.client.messages, "create", return_value=mock_response
        ):
            result = copywriting_service.generate_dm(lead_data, sample_client_config)

        assert isinstance(result, str)
        assert len(result) > 0
        # Should not contain markdown or JSON formatting
        assert "```" not in result
        assert "{" not in result

    def test_generate_dm_no_research(
        self, copywriting_service, sample_lead_data, sample_client_config
    ):
        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text="Hey, vi tu perfil de marketing y me parecio interesante. Nosotros ayudamos a negocios similares a conseguir mas clientes con automatizacion. Quieres saber mas?"
            )
        ]

        lead_data = {**sample_lead_data, "research_data": "No research available"}

        with patch.object(
            copywriting_service.client.messages, "create", return_value=mock_response
        ):
            result = copywriting_service.generate_dm(lead_data, sample_client_config)

        assert isinstance(result, str)
        assert len(result) > 0

    def test_dm_does_not_contain_forbidden_words(
        self, copywriting_service, sample_lead_data, sample_client_config
    ):
        forbidden_words = ["journey", "game-changer", "impressive", "amplify", "transformation"]
        dm_text = "Hey, me gusto tu perfil de marketing. Nosotros ayudamos a agencias con automatizacion de leads. Te interesa?"

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=dm_text)]

        lead_data = {**sample_lead_data, "research_data": "No research available"}

        with patch.object(
            copywriting_service.client.messages, "create", return_value=mock_response
        ):
            result = copywriting_service.generate_dm(lead_data, sample_client_config)

        for word in forbidden_words:
            assert word.lower() not in result.lower()
