"""Camada de domínio do Legendar.

Regras de negócio puras: sem Qt, sem FFmpeg, sem rede e sem filesystem. Se um
módulo desta camada precisar de um desses recursos, a dependência deve ser
invertida por meio de uma porta em ``legendar.application.ports``.
"""
