"""Carga pequena e fictícia; nenhum trajeto ou documento representa dados reais."""

MERCADORIAS = [
    {
        "_id": "DEMO-MER-001",
        "descricao": "Mercadoria de demonstração",
        "especificacoes_tecnicas": {},
        "especificacoes_fiscais": {},
        "demonstracao": True,
    }
]

LOTES = [
    {
        "_id": "DEMO-LOT-001",
        "mercadoria_id": "DEMO-MER-001",
        "quantidade": 100,
        "unidade": "unidade",
        "local_id": "DEMO-CD-001",
        "demonstracao": True,
    },
    {
        "_id": "DEMO-LOT-002",
        "mercadoria_id": "DEMO-MER-001",
        "quantidade": 50,
        "unidade": "unidade",
        "local_id": "DEMO-CD-001",
        "demonstracao": True,
    },
]

VEICULOS = [
    {
        "id": "DEMO-VEI-001",
        "_id": "DEMO-VEI-001",
        "nome": "Veículo de demonstração A",
        "latitude": 0.0,
        "longitude": 0.0,
        "velocidade_kmh": 0.0,
        "temperatura_c": 20.0,
        "demonstracao": True,
    },
    {
        "id": "DEMO-VEI-002",
        "_id": "DEMO-VEI-002",
        "nome": "Veículo de demonstração B",
        "latitude": 0.001,
        "longitude": 0.001,
        "velocidade_kmh": 0.0,
        "temperatura_c": 21.0,
        "demonstracao": True,
    },
]

# x/y servem somente ao esquema da interface, sem correspondência cartográfica.
LOCAIS = [
    {
        "id": "DEMO-CD-001", "nome": "Centro A (demonstração)",
        "tipo": "CentroDistribuição", "operante": True,
        "x": 0.12, "y": 0.5, "demonstracao": True,
    },
    {
        "id": "DEMO-PT-001", "nome": "Transbordo A (demonstração)",
        "tipo": "PontoTransbordo", "operante": True,
        "x": 0.5, "y": 0.18, "demonstracao": True,
    },
    {
        "id": "DEMO-PT-002", "nome": "Transbordo B (demonstração)",
        "tipo": "PontoTransbordo", "operante": True,
        "x": 0.5, "y": 0.82, "demonstracao": True,
    },
    {
        "id": "DEMO-CLI-001", "nome": "Cliente A (demonstração)",
        "tipo": "Cliente", "operante": True,
        "x": 0.88, "y": 0.5, "demonstracao": True,
    },
]

TRECHOS = [
    {"id": "T1", "origem_id": "DEMO-CD-001", "destino_id": "DEMO-PT-001", "distancia_km": 8.0, "operante": True, "demonstracao": True},
    {"id": "T2", "origem_id": "DEMO-PT-001", "destino_id": "DEMO-CLI-001", "distancia_km": 12.0, "operante": True, "demonstracao": True},
    {"id": "T3", "origem_id": "DEMO-CD-001", "destino_id": "DEMO-CLI-001", "distancia_km": 30.0, "operante": True, "demonstracao": True},
    {"id": "T4", "origem_id": "DEMO-CD-001", "destino_id": "DEMO-PT-002", "distancia_km": 9.0, "operante": True, "demonstracao": True},
    {"id": "T5", "origem_id": "DEMO-PT-002", "destino_id": "DEMO-CLI-001", "distancia_km": 14.0, "operante": True, "demonstracao": True},
]

ROTAS = [
    {
        "id": "DEMO-ROT-001",
        "origem_id": "DEMO-CD-001",
        "destino_id": "DEMO-CLI-001",
        "trechos_ids": ["T1", "T2"],
        "distancia_total_km": 20.0,
        "demonstracao": True,
    }
]
