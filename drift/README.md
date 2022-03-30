# Install

Install Solana

```sh
sh -c "$(curl -sSfL https://release.solana.com/v1.9.13/install)"
```

Install Rust

```sh
curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh
```

Install Anchor CLI

```sh
npm i -g @project-serum/anchor-cli
```

Switch to devnet

```sh
solana config set --url devnet
```

Create a Wallet in your browser using phantom then recover it

```sh
solana-keygen recover 'prompt:?key=0/0' --outfile ~/.config/solana/id.json
```

No need to fund the wallet, we're just querying the api not making any trades

# Useful Sites

https://github.com/drift-labs/example-bots/blob/master/src/arbitrage-bot.ts
https://github.com/0xbigz/driftpy-arb
https://docs.drift.trade/sdk-documentation
