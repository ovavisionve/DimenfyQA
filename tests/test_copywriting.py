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

    def test_generate_dm_variant_b(
        self, copywriting_service, sample_lead_data, sample_client_config
    ):
        variant_a = "Hey Test, vi que tienes una agencia de marketing. Nosotros ayudamos a agencias a automatizar leads. Te interesa?"
        variant_b_text = "Test, me llamo la atencion tu enfoque en growth marketing. Estamos trabajando con agencias similares en algo que les ha funcionado bien. Quieres que te cuente?"

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text=variant_b_text)]

        lead_data = {**sample_lead_data, "research_data": "Marketing agency in Miami"}

        with patch.object(
            copywriting_service.client.messages, "create", return_value=mock_response
        ):
            result = copywriting_service.generate_dm_variant_b(
                lead_data, sample_client_config, variant_a
            )

        assert isinstance(result, str)
        assert len(result) > 0
        assert result != variant_a

    def test_variant_b_receives_variant_a_in_prompt(
        self, copywriting_service, sample_lead_data, sample_client_config
    ):
        variant_a = "Original DM text here"

        mock_response = MagicMock()
        mock_response.content = [MagicMock(text="Different DM text")]

        lead_data = {**sample_lead_data, "research_data": "No research available"}

        with patch.object(
            copywriting_service.client.messages, "create", return_value=mock_response
        ) as mock_create:
            copywriting_service.generate_dm_variant_b(
                lead_data, sample_client_config, variant_a
            )

            # Verify variant A text was included in the prompt
            call_args = mock_create.call_args
            prompt_content = call_args.kwargs["messages"][0]["content"]
            assert variant_a in prompt_content
