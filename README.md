# 💰 RRFS Finanças

**Controle de gastos pessoais que sincroniza entre os seus aparelhos, sem servidor central e sem entregar seus dados a ninguém.**

Instale no computador de casa e no do escritório: os dois se encontram sozinhos e mantêm os mesmos lançamentos, com ou sem internet. Seus dados ficam nos seus aparelhos, cifrados.

> ⚠️ **Projeto em desenvolvimento.** Funciona e é usado no dia a dia, mas é novo: veja o [status](#-status) antes de confiar nele para tudo.

## ✨ O que ele faz

- ➕ Lançamentos de entrada e saída: criar, editar e excluir
- 🏷️ Categorias, orçamentos, metas de economia e empréstimos
- 📥 Importação de extratos em **PDF** e **CSV** (o CSV descobre as colunas sozinho)
- 📊 Relatórios, tendências, inflação pessoal e planejamento financeiro
- 🔄 Sincronização automática entre aparelhos, online ou na rede local
- 📴 Funciona offline: sincroniza quando os aparelhos se reencontram
- 💾 Backup cifrado (`.rrfs`) e troca de senha mantendo os dados

## 🔄 Como funciona a sincronização

```
 PC de casa  ◄──── rede Tox (cifrada de ponta a ponta) ────►  PC do escritório
      ▲                                                            ▲
      └──────── mesma rede local: se encontram direto ─────────────┘
```

Não existe conta em servidor. O **usuário e a senha** geram as chaves da conta; quem digita os mesmos em outro aparelho entra na mesma rede. A comunicação usa o protocolo [Tox](https://tox.chat/).

## 🔒 Segurança e privacidade (sem exageros)

**O que o projeto garante**
- Dados guardados só nos seus aparelhos, em banco cifrado (SQLCipher, AES-256).
- Comunicação entre aparelhos cifrada de ponta a ponta.
- Nenhuma coleta de dados, anúncio ou rastreamento. O código é aberto: confira.

**O que você precisa saber**
- 🔑 **A senha é a chave de tudo e não há recuperação.** Use uma frase longa (4 palavras ou 12+ caracteres) e faça backup.
- 💾 **Você é responsável pelos dados.** Use mais de um aparelho e exporte backups para um lugar seguro. O arquivo de backup é cifrado com a frase que você escolher.
- 🌐 Para se encontrarem pela internet, os aparelhos usam **nós públicos da rede Tox** só para localizar uns aos outros. Eles não recebem seus dados, mas o seu IP pode aparecer na rede.
- 🧱 Quando a rede bloqueia as portas padrão, o app cai para relays TCP (inclusive porta 443). Isso dificulta bloqueios, mas **não garante** contra censura.
- Trocar a senha **não expulsa** quem já a tinha e já estava sincronizado.
- Não houve auditoria externa da criptografia. Revisões são bem-vindas.

## 📦 Instalação

### Linux (Debian/Ubuntu e derivados)

```bash
git clone https://github.com/Rafael-Ricardo10/RRFS_Gastos_Pessoais.git
cd RRFS_Gastos_Pessoais
chmod +x install.sh
./install.sh
```

O instalador coloca o app em `~/.local/share/Gastos_Pessoais/`, cria o atalho no menu (categoria Escritório) e, se você quiser, o início automático com o sistema. Seus dados ficam em `~/.local/share/Gastos_Pessoais/dados/` e **nunca são apagados** ao atualizar.

Opções: `--sem-autostart` · `--sem-apt` · `--desinstalar`

### Windows 10/11 (experimental)

Dê dois cliques em `install.bat` (ou rode no terminal). Ele instala em `%LOCALAPPDATA%\Gastos_Pessoais`, cria o atalho no Menu Iniciar e o início automático. Para remover: `install.bat /desinstalar`.

> O instalador do Windows ainda **não foi testado de ponta a ponta**. Se falhar, abra uma Issue com a mensagem de erro.

### Rodar direto do código

```bash
pip install -r requirements.txt
python3 app.py --autoteste   # confere se tudo está presente
python3 app.py
```

## 📥 Importando extratos

- **CSV:** funciona com qualquer banco que exporte CSV; o app descobre separador, colunas, datas e valores. Em fatura de cartão com valores trocados, use "Inverter entrada/saída".
- **PDF:** depende do layout de cada banco.
- ✅ Testado com extratos do **Sicredi**. Outros bancos: relate o que acontecer.

## 🧪 Status

| Parte | Situação |
|---|---|
| Desktop Linux | ✅ em uso e testado |
| Desktop Windows | 🧪 instalador experimental |
| Android | 🚧 interface pronta, APK ainda em testes |
| iPhone | ❌ não previsto por enquanto |
| Extrato online (sem importar arquivos) | 🔍 em estudo |

Encontrou um problema? [Abra uma Issue](../../issues). Seu feedback ajuda muito.

## 🙏 Agradecimento

À comunidade do projeto **Tox**. Por ser aberto, o protocolo ([c-toxcore](https://github.com/TokTok/c-toxcore)) tornou possível este projeto. Sem esse trabalho colaborativo, o RRFS Finanças não existiria.

## ❤️ Apoie o projeto

Doações são bem-vindas e me incentivam a continuar.

| Forma | Chave |
|---|---|
| PIX | `0cd822ec-e5a8-48cb-b17f-a9c4233c7b59` |
| Bitcoin (BTC) | `bc1qqz3l07skhpvh4k5dzhcgyh342c76f2y4vmka27` |

## 🤝 Contribuindo

Sugestões, relatos de bugs e Pull Requests são bem-vindos. Para mexer na rede ou na criptografia, descreva o que mudou e como testou.

## 📄 Licença

Veja o arquivo [`LICENSE`](LICENSE).
