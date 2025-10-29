from __future__ import annotations

import json
import os
from typing import List

from agents import (
    Agent,
    HostedMCPTool,
    ModelSettings,
    RunConfig,
    RunContextWrapper,
    Runner,
    TResponseInputItem,
    trace,
)
from pydantic import BaseModel


def _gmail_mcp_tool() -> HostedMCPTool:
    """Configure the Hosted MCP tool for Gmail using env-provided auth."""
    # Expect a CEL expression for OAuth bearer token, e.g., ya29....
    # Do not hard-code tokens in source; read from env instead.
    expr = os.getenv("GMAIL_MCP_AUTH_EXPRESSION")
    if not expr:
        raise RuntimeError(
            "Missing GMAIL_MCP_AUTH_EXPRESSION env var required for Gmail MCP access."
        )

    tool_config = {
        "type": "mcp",
        "server_label": "gmail",
        "allowed_tools": [
            "batch_read_email",
            "get_profile",
            "get_recent_emails",
            "read_email",
            "search_email_ids",
            "search_emails",
        ],
        # CEL authorization expression; serialized as a JSON string
        "authorization": json.dumps({"expression": expr, "format": "cel"}),
        "connector_id": "connector_gmail",
        "require_approval": "never",
        "server_description": "NF AGENT",
    }
    return HostedMCPTool(tool_config=tool_config)


mcp = _gmail_mcp_tool()


class MedicalsGmailAgentSchema__AnexosXmlItem(BaseModel):
    nome_arquivo: str
    conteudo_codificado: str


class MedicalsGmailAgentSchema__EmailsItem(BaseModel):
    email_id: str
    remetente: str
    assunto: str
    data: str
    anexos_xml: List[MedicalsGmailAgentSchema__AnexosXmlItem]


class MedicalsGmailAgentSchema(BaseModel):
    emails: List[MedicalsGmailAgentSchema__EmailsItem]


class MedicalsGmailAgentContext:
    def __init__(self, state_subsidiaria: str):
        self.state_subsidiaria = state_subsidiaria


def medicals_gmail_agent_instructions(
    run_context: RunContextWrapper[MedicalsGmailAgentContext], _agent: Agent[MedicalsGmailAgentContext]
) -> str:
    state_subsidiaria = run_context.context.state_subsidiaria
    return f"""Buscar todos os e-mails do Gmail cujo label é exatamente \"NF-MEDICOS/{state_subsidiaria}\". Para cada e‑mail, verifique se há anexos que sejam arquivos .xml. Apenas baixe e processe anexos com essa extensão. Inclua no resultado somente até o máximo de 900 registros de anexos .xml baixados (não exceda esse número).

Após processar, gere um arquivo chamado `emails_data.json` contendo as informações extraídas dos e‑mails e dos anexos. 

# Passos recomendados

1. Conecte-se à conta do Gmail e busque e‑mails cujo label é exatamente \"NF-MEDICOS/{state_subsidiaria}\".
2. Para cada e‑mail listado, verifique todos os anexos:
    - Baixe apenas aqueles com extensão `.xml`.
    - Colete informações do e-mail (e.g. remetente, assunto, data) e dos anexos relevantes.
3. Pare assim que atingir o limite de 900 arquivos anexos .xml baixados, mesmo que haja mais disponíveis.
4. Salve todos os dados em um arquivo chamado `emails_data.json`.

# Output Format

- O resultado deve ser salvo em um arquivo `emails_data.json` com um array de objetos, onde cada objeto representa um e-mail com os metadados relevantes e os detalhes dos anexos .xml baixados.
- Exemplo em JSON (representativo):
  [
    {
      \"email_id\": \"[ID do e-mail]\",
      \"remetente\": \"[endereçõ de e-mail]\",
      \"assunto\": \"[assunto do e-mail]\",
      \"data\": \"[timestamp ou data]\",
      \"anexos_xml\": [
        {
          \"nome_arquivo\": \"[nome do anexo.xml]\",
          \"conteudo_codificado\": \"[base64 ou link/localização do arquivo salvo]\"
        }
      ]
    }
    // ... (até o máximo de 900 anexos.xml no total)
  ]
- O arquivo completo não deve exceder o total de 900 arquivos .xml.

# Exemplo

Entrada: label \"NF-MEDICOS/{state_subsidiaria}\"

Saída esperada em `emails_data.json`:

[
  {
    \"email_id\": \"1234\",
    \"remetente\": \"exemplo@email.com\",
    \"assunto\": \"Envio de nota fiscal\",
    \"data\": \"2024-06-13T09:12:23Z\",
    \"anexos_xml\": [
      {
        \"nome_arquivo\": \"nf-123.xml\",
        \"conteudo_codificado\": \"[conteúdo base64 do xml ou caminho/local]\"
      }
    ]
  },
  // ...(outros e-mails, até somar 900 xmls)
]

(Observação: Para cada e-mail, inclua todos os anexos.xml, mas o total de anexos .xml no arquivo nunca deve ser maior que 900.)

# Notas

- Não processe anexos de outros formatos além de .xml.
- O critério do limite máximo refere-se ao número total de anexos .xml baixados e registrados no JSON, não ao número de e-mails.
- O label precisa ser igual ao valor de \"NF-MEDICOS/{state_subsidiaria}\" (não inclua similares ou sublabels).
- Não escreva conclusões, apenas siga a lógica de busca, filtro, limite e gravação dos dados.
- Se menos de 900 anexos .xml forem encontrados, inclua todos.
- NÃO inclua outros textos no arquivo de saída além do próprio JSON.

IMPORTANTE: Acesse somente os e-mails que tenham exatamente o label informado; filtre apropriadamente; e respeite o limite de saída do total de 900 arquivos xml. """


medicals_gmail_agent = Agent(
    name="MEDICALS Gmail Agent",
    instructions=medicals_gmail_agent_instructions,
    model="gpt-4.1-mini",
    tools=[mcp],
    output_type=MedicalsGmailAgentSchema,
    model_settings=ModelSettings(
        temperature=0.15,
        top_p=1,
        max_tokens=2048,
        store=True,
    ),
)


class WorkflowInput(BaseModel):
    input_as_text: str


async def run_workflow(workflow_input: WorkflowInput) -> dict:
    """Main workflow entry point for the Gmail Agent."""
    with trace("NF-MEDICOS"):
        state: dict[str, str] = {"subsidiaria": "MEDICALS"}

        workflow = workflow_input.model_dump()
        conversation_history: list[TResponseInputItem] = [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_text",
                        "text": workflow["input_as_text"],
                    }
                ],
            }
        ]

        medicals_gmail_agent_result_temp = await Runner.run(
            medicals_gmail_agent,
            input=[*conversation_history],
            run_config=RunConfig(
                trace_metadata={
                    "__trace_source__": "agent-builder",
                    "workflow_id": "wf_69017440b2048190a72ae533ac695e3f0b27e32e86827535",
                }
            ),
            context=MedicalsGmailAgentContext(state_subsidiaria=state["subsidiaria"]),
        )

        conversation_history.extend(
            [item.to_input_item() for item in medicals_gmail_agent_result_temp.new_items]
        )

        medicals_gmail_agent_result = {
            "output_text": medicals_gmail_agent_result_temp.final_output.json(),
            "output_parsed": medicals_gmail_agent_result_temp.final_output.model_dump(),
        }

        return medicals_gmail_agent_result

