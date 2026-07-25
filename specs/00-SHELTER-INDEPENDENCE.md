# Shelter Independence — 「Mac を売っても死なない」spec（順序の正本）

done="Franklin 本体が Nosana 上で常駐稼働し、Mac mini を停止しても lease 更新・署名・応答が続き、その第三者検証可能な証拠が揃って記事を publish できる"

方式: superpowers (Obra)。vcsdd は使わない（恒久ルール）。

## 検証済みの現状（2026-07-26 実測）

| 事実 | 証拠 |
|---|---|
| 自己資金で Nosana job を購入・応答確認済み | job `5dvaC3H2gB8Pfh…` IPFS ログ + HTTP/2 200（前セッション実測） |
| 現行 deploy は post して終了する一発屋 | `skills/self/shelter/nosana/deploy.mjs` — post→reconcile→return のみ。lease 監視・延長・再署名ループなし |
| 現行 job の中身は nginx:alpine（署名も agent もなし） | `deploy.mjs:24` `DEFAULT_IMAGE = "docker.io/library/nginx:alpine"` |
| `--confidential` は未実装・未使用 | `nosana/` 配下に "confidential" 出現ゼロ（rg 実測） |
| Franklin = `@blockrun/franklin`（Solana 自己資金 agent） | `life-manager-8i-cutover/README.md:48-53` |
| S9 の作業はディスク上に存在しない | anicha repo: commit 2件のみ・working tree clean・worktree なし。「走行中」は前会話内の申告で、実体なし |
| job definition は公開 IPFS に載る（in-job secrets 不可） | memory: nosana-shelter-hard-constraints |

## 残 TODO（この表が順序の正本。番号順に着手）

### A. 生存 — 「Mac を売っても死なない」3段（記事の本体）

| 順 | ID | 内容 | 状態 |
|---|---|---|---|
| 1 | S9 | 常駐化 — post して exit する現行を、lease 全期間ループへ。lease 中に伸びた timeout の再読含む。毎サイクル新しい blockhash で署名 = 「ずっと生きていた」の第三者検証可能な証拠。container 側も nginx でなく署名 loop を積む | 未着手（前会話の「走行中」はディスクに実体なし） |
| 2 | S8 | SPL Approve 委任 — spend 上限を Solana on-chain で強制。委任鍵が漏れても上限以上盗まれない。信頼できるサーバ不要の唯一の設計 | 未着手・最重要 |
| 3 | S13 | `--confidential` job 実測 — ベンダー自身の秘密投入機構。definition が公開 IPFS に載らない。`--wait` 必須・ログはライブのみ。一度も未試行 | 未着手（S8 の代替/補完） |
| 4 | S12 | Franklin 本体を Nosana へ（BASE_CHAIN_WALLET_KEY / CDP_API_KEY_* が要るので S8 or S13 が前提） | 未着手 |
| 5 | S14 | 独立の最終テスト — **Mac 全体は落とさない**（他の稼働系が載っているため）。Franklin/shelter 関連の Mac 側プロセスだけを停止し、Nosana 側が lease 更新・署名・応答を単独で続けることを実測。「Mac が消えても死なない」ことの証明であって、Mac を実際に消すことではない | S9+S8 の後 |

### B. 稼ぎ（$1.15/日 → 実 payout）

| 順 | ID | 内容 | 状態 |
|---|---|---|---|
| 6 | T2b | discovery catalog 登録 — 到達可能だが発見不可能 | 🔴 revenue $0 の残りの壁 |
| 7 | E7 | Gig を banked まで（実 payout rail） | 未着手 |
| 8 | F1 / T2 | トレードループ + 理由報告 / 稼ぎ面仕上げ | 🔄 |
| 9 | T2c | serve-mainnet.mjs 自己決済 — ETH $0.0165 で gas 不足、売れても決済不能 | 要 gas |
| 10 | S10 | 完成経路でブリッジ（片脚ブリッジは撃たない） | 🔄 |

### C. 記録・その他（A/B の後）

| ID | 内容 |
|---|---|
| A1 | 証拠パッケージ |
| T3b | 財務日報 |
| E5 | lane attribution |
| S11 | deployments 正規経路 |
| S4b | snapshot 自動化 |
| E6 | （未定義タスク — 前会話参照） |
| S5 | 再帰 self-host |
| E8 / E9 | 24h・7+14日 生存計測 |
| E1 | external — BLOCKED |
| F1-scale | $5,000 まで凍結 |

## 記事のゲート

- 今証明済み: 「自分の金で家を借り、自分で更新し、家が応答し、中でコードが走った」— これだけでも公開前例なし（検索で見つからず）
- Dais が書きたい記事: 「Mac を売っても生きている」— S9 + S8（+S14 実測）が必須
- 判断: S9 → S8 を通してから書く。mock/fake の実績は一切書かない

## 参照

- 実装: `skills/self/shelter/nosana/`（deploy.mjs / job-definition.mjs / market.mjs / spend-gate.mjs / keypair.mjs / funding/acquire-nos.mjs）
- 制約 memory: nosana-shelter-hard-constraints（公開 IPFS・CLI extend/post 破損・no persistence）
- Franklin: `@blockrun/franklin`（npm）、参照 `~/Projects/life-manager-8i-cutover/README.md:48`
