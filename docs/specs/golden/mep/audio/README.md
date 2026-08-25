# Seção `audio` do pack de exemplo

O alvo deste golden é um jogo Game Boy (`F1 Test Tone`). A seção `audio`
para GB/SMS depende do freeze da extensão
[`hires-gbsms-v1-draft.md`](../../../hires-gbsms-v1-draft.md) e **ainda não
é aplicada pelo host MesenCE** (ADR-0041 — no v1 só `nes` recebe áudio, via
um `hires.txt` com tags `<bgm>`/`<sfx>` apontando para arquivos OGG nesta
pasta). A pasta existe para que o pack.json golden aponte para um caminho
real; quando a extensão congelar, o conteúdo entra aqui sem mudar o
`pack.json`.
