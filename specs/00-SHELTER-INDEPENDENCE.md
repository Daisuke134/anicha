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
| 1 | S9 | 常駐化 — lease 全期間ループ + timeout 再読 + 毎サイクル blockhash 署名 | ✅ **完了 2026-07-26**。実測: live job `AnubczGS5FZmyqrEtv7AwJ2b7Ks1f7TTsYQ7HK2u3meo`（$0.012 自費）に steward attach、queued→running→success の全 lease を 14 cycles 常駐、`citizen-steward --verify --rpc` = **14/14 PASS（全署名有効 + 全 blockhash が実 slot と on-chain 一致）**。実装 main merge 済み（heartbeat.mjs / steward.mjs / bin/citizen-steward、77/77 tests、review PASS）。container 側の署名 loop は S12 で Franklin 本体ごと載せる |
| 2 | S8 | **sub-wallet 方式**で on-chain spend cap（設計転換 2026-07-26）。SPL Approve 委任は不可 — nosana-jobs `list.rs` の Anchor constraint が `user == payer 自身の ATA` を強制し delegate 経路を遮断（一次ソース: nosana-ci/nosana-programs list.rs + solana-program/token processor.rs L273-290、research agent 検証済み）。代替 = cap 分の NOS + 少額 SOL だけ入金した hot sub-wallet を作り、その鍵のみ cloud へ。cap 強制 = 残高そのもの（SOL 側も cap される分 delegate より強い）。@nosana/sdk `list(..., payer=subWallet)` が公式に payer 分離対応。refund も sub-wallet ATA に閉じる | ✅ **完了 2026-07-26**。E2E 実測: job `DzeUu64JRuFu8kNEnnwejUp5xkNjwPr1hm6fZRsk7zWW` を sub-wallet 支払いで post→16 cycles 常駐→success、escrow 残の refund も sub-wallet に返還確認（0.3077 NOS 残）。steward の slot/blockhash 分離 race も発見・修正（atomic *AndContext 化 + regression test）。review 指摘4件対応、main merge 済み。（旧記録: 実装 merge 待ち（branch `s8-subwallet`: sub-wallet.mjs + bin/citizen-subwallet + NOSANA_KEYPAIR_PATH override、88/88 tests）。実測済み: sub-wallet `71FfqFniYoMsWZb1qFeQDb1fk2xqvajzivpsnMb44gTf` を 0.35 NOS + 0.006 SOL で fund（sigs: 4YhApife… / 51A5Fnpx… / Q16AP7pD… / AaMhHDaz…）→ **job `DzeUu64JRuFu8kNEnnwejUp5xkNjwPr1hm6fZRsk7zWW` を sub-wallet 支払いで post 成功（API 実測 payer=71Ffq…）**、steward attach 済み。発見: CLI は escrow で `timeout 分の NOS`（0.3384）を要求 — estimateJobCost の見積($0.012)と別物、未使用分は返金。fee floor gate が SOL 0.004 を正しく拒否した実績も記録）| 
| 3 | S13 | `--confidential` job 実測 — ベンダー自身の秘密投入機構 | 🔄 **核心実証済み 2026-07-26**: confidential job `HsUW6Spd8Dzx5oXAfLB5ndQabfdVWPBGA4skAuJkWqQX` を live post（10分・owner 支払い）→ 公開 IPFS の CID `QmYBbVdW…` を ipfs.io + pinata の両 gateway で fetch = **stub のみ**（`ops:[]`, `logistics: api-listen`）— image/cmd/env は IPFS に載らない。`--confidential` は buildPostArgs 経由で実装済み（90/90 tests、branch `s13-confidential`）。✅ **完了 2026-07-26**。第2実証: poster CLI が死んだ状態では node は claim 後 `waiting-for-job-definition` で終了（state 2、timeStart 1785006025→timeEnd 1785006689 実測）= **confidential は poster プロセス常駐が必須**。未使用 escrow は返金確認（実験コスト ~0.028 NOS）。S12 への設計制約: confidential post は `--wait` 付きで長命プロセスとして spawn し、steward がその生存を管理する |
| 4 | S12 | Franklin 本体を Nosana へ | 🔄 **E2E 走行中 2026-07-26**。設計確定: sub-wallet が家賃 payer 兼 Franklin cloud 鍵（`.solana-session`=sub-wallet secret を confidential env で搬送、正本鍵は Mac を出ない）。branch `s12-franklin`: USDC leg + franklin-job.mjs + confidential-post.mjs（detached `--wait` poster）+ bin/citizen-franklin-up、98/98 tests。実測: USDC $0.025 fund（sig 2GkU2Ukj…）→ **confidential job `EGJ8SBtTUcbhSDRbEGTGVPsgfk56yty1DPhwraSPiMEE` post 成功**（poster pid 常駐、steward attach 済み）。発見: escrow 要求は duration 非依存で 0.3384 NOS 固定。CLI は最低 0.005 SOL も要求。**確定した3知見**: ①moveCursor TTY crash は NODE_OPTIONS preload shim（shim/tty-shim.cjs）で根治 — poster が --wait で完走生存 ②confidential の定義搬送は poster→node の HTTP POST（postJobDefinitionUntilSuccess）で、poster 生存中なら成功（J4FW で実証: retrieved→validated→container started） ③**cmd は array 不可**: ["sh","-c",script] は node 側で ~3s 死、フラット文字列 cmd は稼働（A/B: probe job `6ceJBBkf…` の "probe up" が poster に stream された）。franklin def を string cmd に修正済み。✅ **本体達成 2026-07-26**: job `3DUJeSYDZdDFmZXr4u3hDbxuztWXysokEemQzn4fgUxt` で **Franklin が Nosana container 内で実走** — npm install→鍵展開→`franklin start` 実行→model 応答を生成→proof server が外部公開 URL `https://3qrxT3AofDWoUYcxh1ktV8NCz5g72JK6oNU5XftfMoA4.node.k8s.prd.nos.ci` で応答（実測 fetch、証拠: specs/evidence/s12-proof-3DUJeSYD.txt）。家賃は sub-wallet が on-chain 支払い、秘密は confidential p2p のみ、heartbeat 4/4 PASS。**S12b ✅ 解決 2026-07-26 — 「$5 デポジット床」は誤り（俺の前提ミス）**。実測: BlockRun は **Base の x402 で $0.003/call**（`POST https://blockrun.ai/api/v1/chat/completions` の 402 header = eip155:8453・USDC・amount 3000・payTo 0xe9030014…、デポジット床なし）。**founder wallet から実決済成功: HTTP 200 + gpt-5-mini の実出力、PAID tx `0x3abb9b69aab7…` success:true、USDC $4.995→$4.992**（`scripts/blockrun-buy.mjs`）。真因 = cloud Franklin が **Solana rail** で払おうとして verification に落ちていた。**修正方針: cloud Franklin に Base 鍵 + 少額 USDC を confidential env で渡せば有料 frontier が通る**（S12c として実施）|
| 5 | S14 | 独立の最終テスト — Mac 側プロセスだけ停止し Nosana 側の単独生存を実測 | ✅ **完了 2026-07-26**（S12 と同時実証）。手順: Franklin job `3DUJeSYD…` 稼働中に Mac 側の poster(pid 89603) と steward を kill（20:02:41Z、`poster-dead` 確認）→ その後も cloud service URL は **HTTP 200 で Franklin proof を返し続け**、lease は `2 success` で完走（monitor 実測）。= Mac が消えても Nosana 上の Franklin は生存。他の Mac 稼働系は無傷 |

### B. 稼ぎ（agent economy — diversified・全 rail real・dry ゼロ）

**資金の現在地（2026-07-26 実測）**: founder/economy wallet `0x810f6d61…` = **Base USDC $10.10** + ETH ~$0.03。他 colony wallet はほぼ $0（Franklin Solana ~$0.5相当、x402 0x6592=$0、PM 0x4c17=$0、HL 0xB9dd=$0、sol-trade 8Fpqd=$0）。**唯一の実資金 = Base の $10.10。**

**「dry runs じゃない」の保証基準（Dais 要件）**: rail が real か dry かは1点 — 実 tx 署名/実注文→**tx-hash/order-id を on-chain か API で検証→ landing 確認して ledger 記録**。LLM が「buy しろ」と言うだけ = 構造的 dry。payload に fake/dry/mock/phantom が出たら reject。

**trade rail 在庫の実査結果:**
| rail | real 執行? | 判定 |
|---|---|---|
| yield（Aave/Fluid/Beefy, Base）`execute-yield.mjs` | ✅ 実 tx + **phantom-guard**（landing 検証） | 採用・土台 |
| Polymarket `polymarket-trade/run.sh` | ✅ 実 CLOB（cap $2/$20 hard, adversary-reviewed, 実注文試行を実測） | 採用・エッジ（要修理） |
| Hummingbot（clone 実査） | ✅ 40+ venue 実注文の成熟 MM（DEX connector は KYC 不要） | 採用候補・24/7 MM |
| ✗ AutoHedge（`~/autohedge` 実査 633 LOC） | ❌ **LLM agent だけ、venue SDK/place_order 皆無** = 構造的 dry | 不採用 |
| ✗ Franklin-Trading / sol-trade | ❌ 半端（Dais 判定・未完成） | 不採用 |
| ✗ Hyperliquid `hl-trade` | — Dais が明示 OFF | 不採用 |

**diversification 方針**: ①yield（土台・Base 即・負けにくい）②PM（エッジ・修理）③Hummingbot DEX-MM（24/7 機械収入・導入）。単一 venue 非依存・全部 verify 可能・dry ゼロ。tokenized 株は Solana xStocks/Ostium が未配線 gap。

| 順 | ID | 内容 | 状態 |
|---|---|---|---|
| 6 | T2b | x402 discovery 登録 | ✅ **達成**。live `anicca-x402-discovery-production.up.railway.app/prompt-sanitizer`（payTo 0x6592, Base USDC $0.005, bazaar ext）、x402scan register 200 success（resource `3c716f96…`）。残 Task4 = self-buy で CDP Bazaar seeding（要 Base payer） |
| 7 | E7 | Gig を banked | 🔄 実案件 coconala `17943244`（取引中・v23 納品済・acceptance PASS）。**正式納品/検収 2026-08-14**＝banked 予定。外部人間+未来日付で今は強制不能、loop 維持中。本筋外 |
| 8 | **F1 yield** | Base 余剰を yield へ実 deploy | ✅ **達成・on-chain 検証済み 2026-07-26**。$5.10 USDC → **Fluid fUSDC 実着地（shares 4,536,729、5.36% APY、Base）**、$5 は compute reserve 温存。0x810f USDC $10.10→$5.00 を実測。loop の guard は "phantom" と誤検知したが on-chain の fUSDC share 残高で実着地を確認（＝self-report でなく chain で verify する規律が効いた）。**economy 初の real earning position・dry ゼロ**。※guard の phantom 誤検知は要修正（landing チェックが確定前に走る） |
| 9 | **F2 PM** | PM を実 fill に | 🟡 **実態判明 2026-07-26: 壊れてない。資金ゼロ + 勝ち position が満期待ち**。naked wallet `0x904B50d2e214Da947d83D6a2D32c4E3Ffc17Eb74` が「Fed 7月会合 no change」を **8 shares @0.6923 → 現在 0.8035 = 含み益 +$0.89(+16%)**、**決着 2026-07-29**（redeemable=false）。PM 系 wallet（0x904B50/0x4c17/0x99b3）は全て **USDC $0** — allowance エラーは現金ゼロで新規 quote を出そうとした結果。done = ①7/29 決着 → redeem で ~$6.4 現金化（自動、待ち）②現金が入ったら allowance 設定 → cadence 化 → 実 fill。**今すぐ強制できるのは②の allowance 準備のみ、①は満期日待ち** |
| 10 | **F3 Hummingbot** | KYC 不要 DEX connector で MM | ⏸ **保留＝capital-gated（実査 2026-07-26）**。KYC 不要 connector 実在（injective_v2/dexalot/derive/backpack/hyperliquid + gateway AMM）だが ①conda+Cython の重量インストール ②**$5 資本では MM が economically 成立しない**（両サイド在庫を置いて薄いスプレッドを取る商売、手数料/gas に食われる）。コード問題でなく資金問題。**着手条件 = 運用資本 $100+ に到達したら**。今やると「動くが稼がない」＝ dry の親戚 |
| 10b | **F4 x402 self-buy** | 自 endpoint に実決済1件 → CDP Bazaar seeding | ✅ **達成・on-chain 検証済み 2026-07-26**。`scripts/self-buy.mjs`（@x402/fetch + ExactEvmScheme、payer=0x810f≠payTo=0x6592 で INV-7 満たす）→ **HTTP 200 + 実サービス応答**（PII masked JSON）+ payment-response の `success:true, transaction 0x6878a285879527ccdf1a6d8f339c0708c55ec69f…`。**on-chain 実測: payer $5.00→$4.995 / payee $0→$0.005**。= **x402 経路が endpoint 公開→discovery 登録→実決済受領まで全部閉じた**。**掲載確認 2026-07-26**: x402scan = **登録が永続化されている**（再 register で同じ resource id `3c716f96…` + `success:true` + lastUpdated 更新を実測）。CDP Bazaar = settle 直後だが **全 14,257 件をページ走査して未掲載**（indexing 遅延と推定、要再確認）。x402scan の public read API path は非公開（複数候補が 404）。※INV-7 により self-payment は「稼ぎ」ではなく discovery seeding |
| 11 | T2c | serve-mainnet.mjs 自己決済 | 要 gas |
| 12 | S10 | bridge（片脚は撃たない） | Base $10.10 → 稼ぎ場（PM=Polygon 等）。frontier seed と x402 は Base 内完結 |

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

### 発見済みバグ（別タスク化済み）

| ID | 内容 | 証拠 |
|---|---|---|
| S15 | reconcileNosanaJobViaApi の `?payer=` は state-0 (queued) job を返さない → post 成功でも "post-unknown" 誤判定。RPC の List tx から fallback 照合を足す | 実事故 2026-07-26: job `Anubcz…` / tx `5ZSpxbWP…`。chip task_07588a71 |

## 記事のゲート

- 今証明済み: 「自分の金で家を借り、自分で更新し、家が応答し、中でコードが走った」— これだけでも公開前例なし（検索で見つからず）
- Dais が書きたい記事: 「Mac を売っても生きている」— S9 + S8（+S14 実測）が必須
- 判断: S9 → S8 を通してから書く。mock/fake の実績は一切書かない

## 参照

- 実装: `skills/self/shelter/nosana/`（deploy.mjs / job-definition.mjs / market.mjs / spend-gate.mjs / keypair.mjs / funding/acquire-nos.mjs）
- 制約 memory: nosana-shelter-hard-constraints（公開 IPFS・CLI extend/post 破損・no persistence）
- Franklin: `@blockrun/franklin`（npm）、参照 `~/Projects/life-manager-8i-cutover/README.md:48`
