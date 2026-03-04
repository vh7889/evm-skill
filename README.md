# evm-skill

EVM 链钱包操作脚本集合，覆盖批量和单钱包场景：

- 批量生成钱包
- 批量分发/归集原生代币（gas 代币）
- 批量分发/归集 ERC20
- 批量闭源合约调用
- 批量 write_contract（ABI + function + args）
- 批量查询余额（原生币 / ERC20）
- 单钱包转账（原生币 / ERC20）
- 单钱包闭源合约调用
- 通过交易哈希提取 to/value/data（可编辑后再调用）
- 模式C：无 ABI 简单静态参数修改（两步确认后广播）
- 根据 4-byte selector 查询候选函数签名
- 单钱包 write_contract（ABI + function + args）
- 单钱包 Bitget 路由 swap
- 单钱包 OKX 路由 swap（quote/swap/simulate/broadcast）
- 单钱包闭源合约调用（OKX onchain-gateway: simulate+broadcast）
- 单钱包 write_contract（OKX onchain-gateway: simulate+broadcast）
- 批量闭源合约调用（OKX onchain-gateway: simulate+broadcast）
- 批量 write_contract（OKX onchain-gateway: simulate+broadcast）
- OKX 5 个 skill 全接口通用调用（swap / gateway / market / token / portfolio）

## 目录结构

```text
evm-skill/
├── scripts/
├── output/
│   ├── wallet/   # 钱包文件
│   └── log/      # 日志与查询结果
├── SKILL.md
└── README.md
```

## 环境准备

```bash
cd <你的skill目录>/evm-skill
python3 -m venv .venv
source .venv/bin/activate
pip install web3 requests
```

## 通用参数说明

大部分链上脚本都支持以下容错参数：

- `--rpc-backup`：备用 RPC（可重复传多次）
- `--rpc-max-retries`：最大重试次数（默认 4）
- `--rpc-timeout`：RPC 超时秒数（默认 15）
- `--rpc-backoff-base`：指数退避基准秒数（默认 0.4）

Gas 策略：

- 默认动态读取链上实时 `gasPrice`
- 可用 `--gas-price-gwei` 手动覆盖

## 常用脚本（示例）

### 1) 批量生成钱包

```bash
python scripts/batch_generate_wallets.py --project test --count 5
```

输出：`output/wallet/wallet_时间戳-项目名-数量.csv`

### 2) 批量分发原生币

```bash
python scripts/batch_distribute_gas.py \
  --main-private-key "<主私钥>" \
  --wallet-csv output/wallet/wallet_xxx.csv \
  --rpc https://bsc-dataseed.binance.org \
  --threads 3 \
  --amount 0.0002
```

### 3) 批量分发 ERC20

```bash
python scripts/batch_distribute_erc20.py \
  --main-private-key "<主私钥>" \
  --wallet-csv output/wallet/wallet_xxx.csv \
  --token 0x55d398326f99059fF775485246999027B3197955 \
  --rpc https://bsc-dataseed.binance.org \
  --threads 3 \
  --amount 0.1
```

### 4) 批量查询原生币余额

```bash
python scripts/batch_query_gas_balance.py \
  --wallet-csv output/wallet/wallet_xxx.csv \
  --rpc https://eth.llamarpc.com \
  --rpc-backup https://ethereum.publicnode.com \
  --threads 5
```

### 5) 批量查询 ERC20 余额

```bash
python scripts/batch_query_erc20_balance.py \
  --wallet-csv output/wallet/wallet_xxx.csv \
  --token 0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48 \
  --rpc https://eth.llamarpc.com \
  --rpc-backup https://ethereum.publicnode.com \
  --threads 5
```

### 6) 单钱包转原生币

```bash
python scripts/single_transfer_gas.py \
  --private-key "<私钥>" \
  --to 0xReceiverAddress \
  --amount 0.0002 \
  --rpc https://bsc-dataseed.binance.org
```

### 7) 单钱包转 ERC20

```bash
python scripts/single_transfer_erc20.py \
  --private-key "<私钥>" \
  --to 0xReceiverAddress \
  --token 0x55d398326f99059fF775485246999027B3197955 \
  --amount 0.1 \
  --rpc https://bsc-dataseed.binance.org
```

### 8) 单钱包闭源合约调用

```bash
python scripts/single_call_contract.py \
  --private-key "<私钥>" \
  --contract 0xContractAddress \
  --data 0x1234abcd... \
  --rpc https://bsc-dataseed.binance.org
```

### 9) 单钱包 Bitget swap

```bash
python scripts/single_swap_bitget.py \
  --private-key "<私钥>" \
  --rpc https://bsc-dataseed.binance.org \
  --chain bnb \
  --from-contract "" \
  --to-contract 0x55d398326f99059fF775485246999027B3197955 \
  --amount 0.0002
```

### 10) 通过交易哈希提取 to/value/data（可编辑后再调用）

查询并导出参数 JSON：

```bash
python scripts/single_call_by_txhash.py \
  --tx-hash 0xYourTxHash \
  --rpc https://bsc-dataseed.binance.org
```

默认输出到：`output/log/tx_params_时间戳-哈希前8位.json`

### 11) 模式C：无 ABI 简单静态参数修改（两步确认）

第一步 preview（不广播）：

```bash
python scripts/single_edit_calldata_no_abi.py preview \
  --rpc https://bsc-dataseed.binance.org \
  --tx-hash 0xYourTxHash \
  --types address,uint256 \
  --set-items 1=0xYourNewAddress \
  --set-items 2=1000000
```

第二步 execute（必须确认）：

```bash
python scripts/single_edit_calldata_no_abi.py execute \
  --proposal-file output/log/noabi_preview_xxx.json \
  --private-key "<私钥>" \
  --rpc https://bsc-dataseed.binance.org \
  --confirm yes \
  --confirm-token <preview输出token>
```

限制：
- 仅支持简单静态类型（`address`、`uint*`、`int*`、`bool`、`bytes1..bytes32`）
- 动态类型（`bytes/string/tuple/array`）不支持

### 12) 根据 selector 查询函数签名（4byte）

```bash
python scripts/query_selector_4byte.py --selector 0x095ea7b3
```

带 calldata 歧义消解：

```bash
python scripts/query_selector_4byte.py \
  --selector 0x095ea7b3 \
  --calldata 0x095ea7b3...
```

说明：
- 当 selector 命中多个候选函数名时，脚本会做解码兼容性校验并给出 `best_guess` 与 `confidence`
- 若仍有歧义，需人工确认，不要直接自动广播

### 13) 单钱包 write_contract（ABI + function + args）

```bash
python scripts/single_write_contract.py \
  --private-key "<私钥>" \
  --contract 0xContractAddress \
  --abi-file ./abi/erc20.json \
  --function transfer \
  --args-json '["0xReceiverAddress","1000000000000000000"]' \
  --rpc https://bsc-dataseed.binance.org
```

提示：
- 重载函数可加 `--function-signature "transfer(address,uint256)"`
- 也可以不用 `--abi-file`，改为 `--abi-json '<ABI JSON>'`
- ABI 也支持 Solidity 声明文本，如 `function transfer(address,uint) public returns (bool)`
- `address` 参数支持小写输入，会自动转 checksum
- `uint/int` 参数支持字符串输入，会自动转整数

### 14) 批量 write_contract（ABI + function + args）

```bash
python scripts/batch_write_contract.py \
  --wallet-csv output/wallet/wallet_xxx.csv \
  --rpc https://bsc-dataseed.binance.org \
  --threads 3 \
  --contract 0xContractAddress \
  --abi-file ./abi/erc20.json \
  --function approve \
  --args-json '["0xSpenderAddress","1000000000000000000"]'
```

提示：
- 支持断点续跑：`--mode all|failed|pending`
- 默认日志文件：`output/log/<钱包csv名>_write_contract_log.csv`

### 15) 单钱包 OKX swap（先 quote/swap，再 simulate/broadcast）

```bash
python scripts/single_swap_okx.py \
  --private-key "<私钥>" \
  --rpc https://bsc-dataseed.binance.org \
  --chain-index 56 \
  --from-token 0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee \
  --to-token 0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d \
  --amount-wei 200000000000000 \
  --slippage-percent 1
```

### 16) 单钱包闭源合约调用（OKX Gateway 版）

```bash
python scripts/single_call_contract_okx_gateway.py \
  --private-key "<私钥>" \
  --rpc https://bsc-dataseed.binance.org \
  --chain-index 56 \
  --contract 0xContractAddress \
  --value 0 \
  --data 0xYourCalldata...
```

### 17) 单钱包 write_contract（OKX Gateway 版）

```bash
python scripts/single_write_contract_okx_gateway.py \
  --private-key "<私钥>" \
  --rpc https://bsc-dataseed.binance.org \
  --chain-index 56 \
  --contract 0xContractAddress \
  --abi-json 'function approve(address spender,uint256 amount)' \
  --function approve \
  --args-json '["0xSpenderAddress","100000000"]'
```

### 18) 批量闭源合约调用（OKX Gateway 版）

```bash
python scripts/batch_call_contract_okx_gateway.py \
  --wallet-csv output/wallet/wallet_xxx.csv \
  --rpc https://bsc-dataseed.binance.org \
  --threads 3 \
  --chain-index 56 \
  --contract 0xContractAddress \
  --value 0 \
  --data 0xYourCalldata...
```

### 19) 批量 write_contract（OKX Gateway 版）

```bash
python scripts/batch_write_contract_okx_gateway.py \
  --wallet-csv output/wallet/wallet_xxx.csv \
  --rpc https://bsc-dataseed.binance.org \
  --threads 3 \
  --chain-index 56 \
  --contract 0xContractAddress \
  --abi-json 'function enterMarkets(address[] cTokens)' \
  --function enterMarkets \
  --args-json '[["0xCTokenAddress"]]'
```

### 20) OKX DEX Swap 全接口通用调用

```bash
python scripts/okx_dex_swap_api.py \
  --action quote \
  --query-json '{"chainIndex":"56","fromTokenAddress":"0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee","toTokenAddress":"0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d","amount":"200000000000000","swapMode":"exactIn"}'
```

### 21) OKX Onchain Gateway 全接口通用调用

```bash
python scripts/okx_onchain_gateway_api.py \
  --action simulate \
  --body-json '{"chainIndex":"56","fromAddress":"0xYourAddr","toAddress":"0xYourTo","txAmount":"0","extJson":{"inputData":"0x"}}'
```

### 22) OKX DEX Market 全接口通用调用

```bash
python scripts/okx_dex_market_api.py \
  --action price \
  --body-json '{"chainIndex":"56","tokenContractAddress":"0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"}'
```

### 23) OKX DEX Token 全接口通用调用

```bash
python scripts/okx_dex_token_api.py \
  --action search \
  --query-json '{"chainIndex":"56","keyword":"koge"}'
```

### 24) OKX Wallet Portfolio 全接口通用调用

```bash
python scripts/okx_wallet_portfolio_api.py \
  --action all-token-balances-by-address \
  --query-json '{"chainIndex":"56","address":"0xYourAddr"}'
```

## 输出文件说明

- 钱包文件：`output/wallet/*.csv`
- 转账/归集/调用日志：`output/log/*_log*.csv`
- 批量查询结果：`output/log/*_balance_query.csv`

## 安全注意事项

- 生产环境建议使用自建或付费 RPC，降低限流和波动风险
- OKX 相关脚本依赖以下环境变量：`OKX_API_KEY`、`OKX_SECRET_KEY`、`OKX_PASSPHRASE`
- 免责声明：本项目脚本仅用于技术测试与自动化操作示例，链上交易风险与资产损失风险由使用者自行承担。
