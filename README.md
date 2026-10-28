# Mercadinho ERP

Sistema de gerenciamento de compras, fornecedores e estoque desenvolvido em Python, integrado ao Supabase.

## Automação de fornecedores

O projeto possui um simulador de fornecedores que automatiza o ciclo de uma compra:

- Simulação da data de faturamento;
- Definição da UF de origem;
- Cálculo da previsão de entrega;
- Cálculo do frete;
- Simulação da data de recebimento;
- Registro do recebimento;
- Entrada automática dos produtos no estoque.

O processo foi desenvolvido para ser executado automaticamente uma vez por dia, mantendo o histórico das movimentações no Supabase.

## Tecnologias

- Python
- Supabase
- GitHub Actions
- PostgreSQL

## Objetivo

Simular e automatizar processos de compras e logística de um mercadinho, permitindo que os dados sejam posteriormente utilizados em análises e dashboards de BI.
