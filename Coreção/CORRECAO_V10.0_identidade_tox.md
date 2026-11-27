# Correção: `identidade.tox` agora é cifrado em disco

**Origem:** sugestão do iphydf https://github.com/iphydf  (c-toxcore, issue #3170): o `identidade.tox` guardava a chave secreta do Tox sem criptografia, enquanto o resto dos dados era cifrado. Obrigado pela revisão!

## O problema

O arquivo `dados/redes/<id>/identidade.tox` é o *savedata* do Tox e contém a chave secreta do aparelho. Estava protegido só por permissão `0600`. Quem copiasse a pasta `dados/` (disco roubado, backup na nuvem, outro usuário do sistema) poderia se passar por aquele aparelho na rede e receber os dados sincronizados, mesmo com o banco SQLCipher cifrado.

## A correção

- O savedata passa a ser gravado com `tox_pass_encrypt` e lido com `tox_pass_decrypt` (ambos da libtoxcore).
- A passphrase vem do login: `HKDF(chave mestra, "tox-save")`, nova derivação em `identidade.py` (`Chaves.chave_tox`). Nenhuma chave existente muda, então as contas atuais seguem iguais.
- **Migração automática:** um `identidade.tox` antigo, em claro, é lido na primeira abertura e regravado cifrado.
- **Arquivo inválido ou corrompido:** a identidade é derivada do login, então o app recria a mesma chave a partir dela e guarda o arquivo ruim como `identidade.tox.invalido`. Nada se perde.
- **Arquivo cifrado sem chave:** gera erro explícito, nunca é ignorado em silêncio.
- **Gravação:** a cifra roda *fora* da trava do toxcore, para não atrasar o `tox_iterate`. O arquivo é criado com `0600`, usa `fsync` e troca atômica.
- **Pequena correção extra:** a lista de amigos (`_amigos`) agora é percorrida sobre uma cópia, evitando o erro "dictionary changed size during iteration" quando outra thread a altera.

## Arquivos alterados

| Arquivo | Mudança |
|---|---|
| `modulos/tox_financeiro.py` | cifra/decifra do savedata, migração, gancho `_senha_arquivo()`, gravação fora da trava |
| `modulos/identidade.py` | nova `Chaves.chave_tox` |
| `modulos/rede.py` | `_senha_arquivo()` devolve `chaves.chave_tox` |

## Como foi testado (libtoxcore 0.2.20 compilada)

- Arquivo criado cifrado (`toxEsave`, modo 0600), com a chave secreta ausente do conteúdo.
- Reabrir com a mesma senha mantém a identidade.
- Migração de arquivo antigo em claro para cifrado mantém a mesma chave pública.
- Senha errada recria a mesma identidade e guarda `.invalido`.
- Arquivo cifrado sem senha falha com mensagem clara.
- Teste de dois aparelhos (`test_rede2.py`): descoberta, sincronização, latência, desconexão remota e comando pendente continuam funcionando.

## Limitações (transparência)

- Exige uma libtoxcore com `tox_pass_encrypt`/`tox_pass_decrypt` (versões 0.2.x atuais). Com uma lib sem essas funções o app não abre e o autoteste aponta o problema.
- O arquivo antigo em claro pode deixar resíduos no disco (blocos liberados) ou em backups já feitos. Não há como apagar isso com segurança em SSD.
- O `sessao.json` ("manter conectado") continua sem cifra quando o sistema não tem cofre (`keyring`). Sem um segredo guardado em outro lugar, cifrar esse arquivo não adiantaria, então isso segue como limitação documentada.
- O modo de pareamento com servidor antigo (`sync_cliente.py`) não define passphrase e continua gravando como antes.

## Mensagem de commit sugerida

```
Cifra o identidade.tox em disco (tox_pass_encrypt/decrypt)

- passphrase derivada do login (HKDF "tox-save"), sem alterar chaves existentes
- migra automaticamente arquivos antigos em claro
- recria a identidade a partir do login se o arquivo ficar inválido
- grava com fsync/rename atômico e cifra fora da trava do toxcore
- itera _amigos sobre cópia (evita corrida entre threads)

Sugerido por iphydf em TokTok/c-toxcore#3170.
```
