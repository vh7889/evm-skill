---
name: evm-skill
description: 用于 EVM 链钱包与资产操作。需要批量生成钱包、批量分发/归集原生 gas 代币、批量分发/归集 ERC20 代币、批量/单钱包余额查询、批量合约调用、单钱包转账、单钱包合约调用、单钱包私钥 Bitget/OKX 路由 swap、OKX onchain-gateway simulate+broadcast、失败重试、断点续跑时使用。
---

# EVM Skill

## 概述

这个 skill 用于 EVM 链批量与单钱包操作，当前包含 27 个脚本：
- 批量生成钱包
- 批量分发 gas 代币
- 批量归集 gas 代币
- 批量分发 ERC20 代币
- 批量归集 ERC20 代币
- 批量闭源合约调用
- 批量查询 gas 代币余额
- 批量查询 ERC20 代币余额
- 单钱包一对一转 gas 代币
- 单钱包一对一转 ERC20 代币
- 单钱包调用闭源合约
- 单钱包 write_contract（ABI + function + args）
- 单钱包查询 gas 代币余额
- 单钱包查询 ERC20 代币余额
- 批量 write_contract（ABI + function + args）
- 单钱包 Bitget 路由 swap
- 单钱包 OKX 路由 swap
- 单钱包闭源合约调用（OKX Gateway: simulate+broadcast）
- 单钱包 write_contract（OKX Gateway: simulate+broadcast）
- 批量闭源合约调用（OKX Gateway: simulate+broadcast）
- 批量 write_contract（OKX Gateway: simulate+broadcast）
- OKX DEX Swap 全接口通用调用
- OKX Onchain Gateway 全接口通用调用
- OKX DEX Market 全接口通用调用
- OKX DEX Token 全接口通用调用
- OKX Wallet Portfolio 全接口通用调用

## 新增 OKX 功能用途速览（给协作者快速理解）

下面是这次新增能力的“主要用途”和“典型场景”：

- `single_swap_okx.py`
  - 主要用途：单钱包执行 OKX 路由 swap（从问价到上链一条龙）
  - 典型场景：你要快速把 BNB 换成 USDC，并且希望看到 quote/swap/simulate/broadcast 全过程参数与返回

- `single_call_contract_okx_gateway.py`
  - 主要用途：单钱包调用闭源合约时，先用 OKX gateway 做 simulate，再广播
  - 典型场景：你已经有 `to + data + value`，想先确认“不会失败”再上链

- `single_write_contract_okx_gateway.py`
  - 主要用途：单钱包 ABI 函数调用（write_contract）走 OKX gateway simulate+broadcast
  - 典型场景：你用 `function + args` 调合约，想保留 write_contract 参数体验，同时接入 OKX 风险前置检查

- `batch_call_contract_okx_gateway.py`
  - 主要用途：批量闭源合约调用走 OKX gateway simulate+broadcast，并保留断点续跑
  - 典型场景：多钱包批量调用同一段 calldata，希望失败可重跑（`--mode failed`）

- `batch_write_contract_okx_gateway.py`
  - 主要用途：批量 write_contract 走 OKX gateway simulate+broadcast，并保留断点续跑
  - 典型场景：多钱包批量执行同一个 ABI 函数（如 `enterMarkets`、`approve`）

- `okx_dex_swap_api.py`
  - 主要用途：直连 OKX DEX Swap 全接口（6 个 endpoint）的通用入口
  - 典型场景：你只想测 API 返回，不想跑完整签名上链流程；或做二次开发联调

- `okx_onchain_gateway_api.py`
  - 主要用途：直连 OKX Onchain Gateway 全接口（6 个 endpoint）的通用入口
  - 典型场景：单独测 gas/simulate/broadcast/orders，排查链上交易问题

- `okx_dex_market_api.py`
  - 主要用途：查询市场价格、K 线、成交、指数价
  - 典型场景：交易前做行情确认，或做轻量行情看板

- `okx_dex_token_api.py`
  - 主要用途：按名称搜 token、看基础信息、价格信息、排行、持仓分布
  - 典型场景：你拿到一个新 token，先做“识别+核验”再考虑交易

- `okx_wallet_portfolio_api.py`
  - 主要用途：查地址总资产、全 token 余额、指定 token 余额
  - 典型场景：交易前后核对资产变化，或做钱包资产快照

- `okx_api_client.py`
  - 主要用途：OKX 鉴权签名、请求发送、统一响应结构（供所有 OKX 脚本复用）
  - 典型场景：减少重复代码，后续扩展 OKX endpoint 时直接复用

## 运行环境

在 `evm-skill` 目录执行命令，先激活虚拟环境：

```bash
cd <你的skill目录>/evm-skill
source .venv/bin/activate
```

## 输出目录

- 钱包文件默认输出到：`output/wallet/`
- 日志文件默认输出到：`output/log/`

## 常用 RPC（主网）

以下为常用公共 RPC（可能限流或波动），生产环境建议使用自建或付费 RPC。
已在 2026-03-03 做过连通性与链 ID 实测。

- ETH 主网：`https://eth.llamarpc.com`
- BSC：`https://bsc-dataseed.binance.org`
- Base：`https://mainnet.base.org`
- Plasma：`https://rpc.plasma.to`
- Arbitrum：`https://arb1.arbitrum.io/rpc`
- Avalanche C-Chain：`https://api.avax.network/ext/bc/C/rpc`
- Polygon：`https://polygon-bor-rpc.publicnode.com`
- Optimism：`https://mainnet.optimism.io`
- Linea：`https://rpc.linea.build`
- Sei EVM：`https://evm-rpc.sei-apis.com`
- zkSync Era：`https://mainnet.era.zksync.io`
- X Layer：`https://rpc.xlayer.tech`
- opBNB：`https://opbnb-mainnet-rpc.bnbchain.org`
- Morph：`https://rpc-quicknode.morphl2.io`

## 脚本

- `scripts/batch_generate_wallets.py`
  - 批量生成 1-n 个钱包
  - 输出 CSV：`output/wallet/wallet_YYYYMMDD_HHMMSS-项目名-钱包数量.csv`
- `scripts/batch_distribute_gas.py`
  - 主钱包批量分发原生代币（BNB/ETH 等）
- `scripts/batch_collect_gas.py`
  - 分发钱包批量归集原生代币到主钱包
- `scripts/batch_distribute_erc20.py`
  - 主钱包批量分发 ERC20 代币
- `scripts/batch_collect_erc20.py`
  - 分发钱包批量归集 ERC20 代币到主钱包
- `scripts/batch_call_contract.py`
  - 分发钱包批量调用指定合约（value=0，按给定 16 进制 calldata）
- `scripts/batch_query_gas_balance.py`
  - 批量查询钱包原生 gas 代币余额（结果输出到 `output/log`）
- `scripts/batch_query_erc20_balance.py`
  - 批量查询钱包 ERC20 代币余额（结果输出到 `output/log`）
- `scripts/single_transfer_gas.py`
  - 单钱包一对一转原生代币（BNB/ETH 等）
- `scripts/single_transfer_erc20.py`
  - 单钱包一对一转 ERC20 代币
- `scripts/single_call_contract.py`
  - 单钱包调用闭源合约（支持 calldata 与可选 value）
- `scripts/single_write_contract.py`
  - 单钱包 write_contract（输入 ABI + functionName + args）
- `scripts/single_query_gas_balance.py`
  - 单钱包查询原生 gas 代币余额
- `scripts/single_query_erc20_balance.py`
  - 单钱包查询 ERC20 代币余额
- `scripts/batch_write_contract.py`
  - 分发钱包批量 write_contract（输入 ABI + functionName + args）
- `scripts/single_swap_bitget.py`
  - 单一私钥执行 Bitget 路由 swap（EVM）
- `scripts/single_swap_okx.py`
  - 单一私钥执行 OKX 路由 swap（quote -> swap -> simulate -> broadcast）
- `scripts/single_call_contract_okx_gateway.py`
  - 单钱包闭源合约调用，使用 OKX onchain-gateway 先 simulate 再 broadcast
- `scripts/single_write_contract_okx_gateway.py`
  - 单钱包 write_contract，使用 OKX onchain-gateway 先 simulate 再 broadcast
- `scripts/batch_call_contract_okx_gateway.py`
  - 批量闭源合约调用，使用 OKX onchain-gateway 先 simulate 再 broadcast
- `scripts/batch_write_contract_okx_gateway.py`
  - 批量 write_contract，使用 OKX onchain-gateway 先 simulate 再 broadcast
- `scripts/okx_dex_swap_api.py`
  - OKX DEX Swap 6 个 endpoint 通用入口
- `scripts/okx_onchain_gateway_api.py`
  - OKX Onchain Gateway 6 个 endpoint 通用入口
- `scripts/okx_dex_market_api.py`
  - OKX DEX Market 7 个 endpoint 通用入口
- `scripts/okx_dex_token_api.py`
  - OKX DEX Token 5 个 endpoint 通用入口
- `scripts/okx_wallet_portfolio_api.py`
  - OKX Wallet Portfolio 4 个 endpoint 通用入口

## 1) 批量生成钱包

命令：

```bash
python scripts/batch_generate_wallets.py --project <项目名> --count <钱包数量>
```

参数说明：
- `--project`：项目名，会写入 CSV 文件名，例如 `pm`、`op`
- `--count`：生成钱包数量，必须 >= 1
- `--rpc`：可选，自定义链 RPC

示例：

```bash
python scripts/batch_generate_wallets.py --project pm --count 20
```

输出：
- 生成 CSV：`output/wallet/wallet_20260302_115448-pm-20.csv`
- 列：`序号,address,privateKey`

## 2) 批量分发 gas 代币（原生币）

命令（固定数量）：

```bash
python scripts/batch_distribute_gas.py \
  --main-private-key <主钱包私钥> \
  --wallet-csv <钱包CSV文件名> \
  --rpc <RPC地址> \
  --threads <线程数> \
  --amount <固定数量>
```

命令（范围数量）：

```bash
python scripts/batch_distribute_gas.py \
  --main-private-key <主钱包私钥> \
  --wallet-csv <钱包CSV文件名> \
  --rpc <RPC地址> \
  --threads <线程数> \
  --amount-min <最小值> \
  --amount-max <最大值>
```

示例（每个钱包固定 0.0005 BNB）：

```bash
python scripts/batch_distribute_gas.py \
  --main-private-key "$(cat ../wallet_test.txt)" \
  --wallet-csv output/wallet/wallets_first3.csv \
  --rpc https://bsc-dataseed.binance.org/ \
  --threads 3 \
  --amount 0.0005
```

## 3) 批量归集 gas 代币（原生币）

命令：

```bash
python scripts/batch_collect_gas.py \
  --main-address <主钱包地址> \
  --wallet-csv <包含私钥的钱包CSV> \
  --rpc <RPC地址> \
  --threads <线程数>
```

示例：

```bash
python scripts/batch_collect_gas.py \
  --main-address 0x7ec9369df94ccc890030ca9a54e1e9f6096da700 \
  --wallet-csv output/wallet/wallets_first3_with_pk.csv \
  --rpc https://bsc-dataseed.binance.org/ \
  --threads 3
```

## 4) 批量分发 ERC20 代币

命令（固定数量）：

```bash
python scripts/batch_distribute_erc20.py \
  --main-private-key <主钱包私钥> \
  --wallet-csv <钱包CSV文件名> \
  --token <ERC20合约地址> \
  --rpc <RPC地址> \
  --threads <线程数> \
  --amount <固定数量>
```

命令（范围数量）：

```bash
python scripts/batch_distribute_erc20.py \
  --main-private-key <主钱包私钥> \
  --wallet-csv <钱包CSV文件名> \
  --token <ERC20合约地址> \
  --rpc <RPC地址> \
  --threads <线程数> \
  --amount-min <最小值> \
  --amount-max <最大值>
```

可选参数：
- `--token-decimals <decimals>`：不填则自动链上读取

## 5) 批量归集 ERC20 代币

命令：

```bash
python scripts/batch_collect_erc20.py \
  --main-address <主钱包地址> \
  --wallet-csv <包含私钥的钱包CSV> \
  --token <ERC20合约地址> \
  --rpc <RPC地址> \
  --threads <线程数>
```

可选参数：
- `--token-decimals <decimals>`：不填则自动链上读取

## 6) 批量闭源合约调用

命令：

```bash
python scripts/batch_call_contract.py \
  --wallet-csv <包含私钥的钱包CSV> \
  --rpc <RPC地址> \
  --threads <线程数> \
  --contract <合约地址> \
  --data <16进制calldata>
```

示例：

```bash
python scripts/batch_call_contract.py \
  --wallet-csv output/wallet/wallet_20260302_150132-test-5.csv \
  --rpc https://bsc-dataseed.binance.org/ \
  --threads 3 \
  --contract 0x55d398326f99059fF775485246999027B3197955 \
  --data 0x095ea7b30000000000000000000000007ec9369df94ccc890030ca9a54e1e9f6096da700ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff
```

## 7) 批量查询 Gas 代币余额（原生币）

命令：

```bash
python scripts/batch_query_gas_balance.py \
  --wallet-csv <钱包CSV文件名> \
  --rpc <RPC地址> \
  --threads <线程数>
```

可选参数：
- `--mode all/failed/pending`
- `--output-csv <路径>`：不填默认输出到 `output/log`

## 8) 批量查询 ERC20 代币余额

命令：

```bash
python scripts/batch_query_erc20_balance.py \
  --wallet-csv <钱包CSV文件名> \
  --token <ERC20合约地址> \
  --rpc <RPC地址> \
  --threads <线程数>
```

可选参数：
- `--token-decimals <decimals>`：不填则自动链上读取
- `--mode all/failed/pending`
- `--output-csv <路径>`：不填默认输出到 `output/log`

## 9) 单钱包一对一转 Gas 代币（原生币）

命令：

```bash
python scripts/single_transfer_gas.py \
  --private-key <私钥> \
  --to <接收地址> \
  --amount <数量> \
  --rpc <RPC地址>
```

## 10) 单钱包一对一转 ERC20 代币

命令：

```bash
python scripts/single_transfer_erc20.py \
  --private-key <私钥> \
  --to <接收地址> \
  --token <ERC20合约地址> \
  --amount <数量> \
  --rpc <RPC地址>
```

可选参数：
- `--token-decimals <decimals>`：不填则自动链上读取

## 11) 单钱包调用闭源合约

命令：

```bash
python scripts/single_call_contract.py \
  --private-key <私钥> \
  --contract <合约地址> \
  --data <16进制calldata> \
  --rpc <RPC地址>
```

可选参数：
- `--value <数量>`：附带原生币数量，默认 `0`

## 12) 单钱包 write_contract（ABI + function + args）

命令：

```bash
python scripts/single_write_contract.py \
  --private-key <私钥> \
  --contract <合约地址> \
  --abi-file <ABI文件路径> \
  --function <函数名> \
  --args-json '<JSON数组参数>' \
  --rpc <RPC地址>
```

可选参数：
- `--abi-json <ABI字符串>`：与 `--abi-file` 二选一；支持 JSON ABI 和 `function transfer(address,uint256) public returns (bool)` 这类声明
- `--function-signature <函数签名>`：重载函数时建议填写，例如 `transfer(address,uint256)`
- `--value <数量>`：附带原生币数量，默认 `0`

参数容错（write_contract）：
- `address` 参数支持小写地址，脚本会自动转换为 checksum
- `uint/int` 参数支持数字字符串，脚本会自动转为整数类型

## 13) 单钱包查询 Gas 代币余额（原生币）

命令：

```bash
python scripts/single_query_gas_balance.py \
  --address <钱包地址> \
  --rpc <RPC地址>
```

## 14) 单钱包查询 ERC20 代币余额

命令：

```bash
python scripts/single_query_erc20_balance.py \
  --address <钱包地址> \
  --token <ERC20合约地址> \
  --rpc <RPC地址>
```

可选参数：
- `--token-decimals <decimals>`：不填则自动链上读取

## 15) 批量 write_contract（ABI + function + args）

命令：

```bash
python scripts/batch_write_contract.py \
  --wallet-csv <包含私钥的钱包CSV> \
  --rpc <RPC地址> \
  --threads <线程数> \
  --contract <合约地址> \
  --abi-file <ABI文件路径> \
  --function <函数名> \
  --args-json '<JSON数组参数>'
```

可选参数：
- `--abi-json <ABI字符串>`：与 `--abi-file` 二选一；支持 JSON ABI 和 function 声明文本
- `--function-signature <函数签名>`：重载函数时建议填写
- `--value <数量>`：附带原生币数量，默认 `0`
- `--mode all/failed/pending`
- `--log-csv <路径>`：不填默认输出到 `output/log`

## 16) 单钱包 Bitget 路由 Swap（EVM）

命令：

```bash
python scripts/single_swap_bitget.py \
  --private-key <私钥> \
  --rpc <RPC地址> \
  --chain bnb \
  --from-contract <fromToken地址> \
  --to-contract <toToken地址> \
  --amount <固定数量>
```

可选参数：
- `--slippage <百分比>`：例如 `0.5` 表示 0.5%

## 17) 单钱包 OKX 路由 Swap（EVM）

命令：

```bash
python scripts/single_swap_okx.py \
  --private-key <私钥> \
  --rpc <RPC地址> \
  --chain-index 56 \
  --from-token 0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee \
  --to-token 0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d \
  --amount-wei 200000000000000 \
  --slippage-percent 1
```

说明：
- 该脚本按 `quote -> swap -> simulate -> broadcast -> orders` 执行
- 输出包含每一步请求参数和原始响应

## 18) 单钱包闭源合约调用（OKX Gateway 版）

命令：

```bash
python scripts/single_call_contract_okx_gateway.py \
  --private-key <私钥> \
  --contract <合约地址> \
  --data <16进制calldata> \
  --rpc <RPC地址> \
  --chain-index 56 \
  --value 0
```

说明：
- 不替换原 `single_call_contract.py`，是新增版本
- 流程：本地签名 -> `simulate` -> `broadcast` -> `orders`

## 19) 单钱包 write_contract（OKX Gateway 版）

命令：

```bash
python scripts/single_write_contract_okx_gateway.py \
  --private-key <私钥> \
  --contract <合约地址> \
  --abi-json 'function approve(address spender,uint256 amount)' \
  --function approve \
  --args-json '["0x29594a86e1658a34a57e6b505defec563f5259fc","100000000"]' \
  --rpc <RPC地址> \
  --chain-index 56
```

说明：
- 不替换原 `single_write_contract.py`，是新增版本
- ABI / 参数解析规则与原 write_contract 保持一致

## 20) 批量闭源合约调用（OKX Gateway 版）

命令：

```bash
python scripts/batch_call_contract_okx_gateway.py \
  --wallet-csv <包含私钥的钱包CSV> \
  --rpc <RPC地址> \
  --threads <线程数> \
  --contract <合约地址> \
  --value 0 \
  --data <16进制calldata> \
  --chain-index 56
```

说明：
- 不替换原 `batch_call_contract.py`，是新增版本
- 流程：本地签名 -> `simulate` -> `broadcast` -> `orders`

## 21) 批量 write_contract（OKX Gateway 版）

命令：

```bash
python scripts/batch_write_contract_okx_gateway.py \
  --wallet-csv <包含私钥的钱包CSV> \
  --rpc <RPC地址> \
  --threads <线程数> \
  --contract <合约地址> \
  --abi-file <ABI文件路径> \
  --function <函数名> \
  --args-json '<JSON数组参数>' \
  --chain-index 56
```

说明：
- 不替换原 `batch_write_contract.py`，是新增版本
- ABI / 参数解析规则与原 batch_write_contract 保持一致

## 22) OKX DEX Swap 全接口通用调用

命令：

```bash
python scripts/okx_dex_swap_api.py \
  --action quote \
  --query-json '{"chainIndex":"56","fromTokenAddress":"0xeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeeee","toTokenAddress":"0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d","amount":"200000000000000","swapMode":"exactIn"}'
```

支持 actions：
- `supported-chain`
- `get-liquidity`
- `approve-transaction`
- `quote`
- `swap-instruction`
- `swap`

## 23) OKX Onchain Gateway 全接口通用调用

命令：

```bash
python scripts/okx_onchain_gateway_api.py \
  --action simulate \
  --body-json '{"chainIndex":"56","fromAddress":"0xYourAddr","toAddress":"0xYourTo","txAmount":"0","extJson":{"inputData":"0x"}}'
```

支持 actions：
- `supported-chain`
- `gas-price`
- `gas-limit`
- `simulate`
- `broadcast`
- `orders`

## 24) OKX DEX Market 全接口通用调用

命令：

```bash
python scripts/okx_dex_market_api.py \
  --action price \
  --body-json '{"chainIndex":"56","tokenContractAddress":"0x8AC76a51cc950d9822D68b83fE1Ad97B32Cd580d"}'
```

支持 actions：
- `supported-chain`
- `price`
- `trades`
- `candles`
- `historical-candles`
- `index-current-price`
- `index-historical-price`

## 25) OKX DEX Token 全接口通用调用

命令：

```bash
python scripts/okx_dex_token_api.py \
  --action search \
  --query-json '{"chainIndex":"56","keyword":"koge"}'
```

支持 actions：
- `search`
- `basic-info`
- `price-info`
- `toplist`
- `holder`

## 26) OKX Wallet Portfolio 全接口通用调用

命令：

```bash
python scripts/okx_wallet_portfolio_api.py \
  --action all-token-balances-by-address \
  --query-json '{"chainIndex":"56","address":"0xYourAddr"}'
```

支持 actions：
- `supported-chain`
- `total-value-by-address`
- `all-token-balances-by-address`
- `token-balances-by-address`

## 通用规则（转账/归集/调用/swap 脚本）

重跑模式（6 个批量链上脚本通用）：
- `--mode all`：处理全部未成功钱包（默认）
- `--mode failed`：仅处理失败钱包
- `--mode pending`：仅处理未开始钱包

线程建议：
- 普通 RPC：建议 `1-5`
- 付费 RPC：按服务能力提高
- 所有交易脚本默认动态读取链上实时 `gasPrice`，也可用 `--gas-price-gwei` 手动指定
- 所有链上脚本支持 RPC 容错参数：
  - `--rpc-backup`：可重复传入备用 RPC
  - `--rpc-max-retries`：单次调用最大重试次数（指数退避）
  - `--rpc-timeout`：RPC 超时秒数
  - `--rpc-backoff-base`：退避基准秒数

日志规则：
- 分发 gas 日志：`output/log/<钱包csv名>_gas_distribution_log.csv`
- 归集 gas 日志：`output/log/<钱包csv名>_gas_collect_log.csv`
- 分发 ERC20 日志：`output/log/<钱包csv名>_erc20_distribution_log.csv`
- 归集 ERC20 日志：`output/log/<钱包csv名>_erc20_collect_log.csv`
- 合约调用日志：`output/log/<钱包csv名>_contract_call_log.csv`
- write_contract 日志：`output/log/<钱包csv名>_write_contract_log.csv`
- OKX 闭源合约调用日志：`output/log/<钱包csv名>_contract_call_okx_gateway_log.csv`
- OKX write_contract 日志：`output/log/<钱包csv名>_write_contract_okx_gateway_log.csv`
- 字段包含：`转出地址`、`接收地址`、`成功哈希`、`失败原因`、`时间`
- 未开始记录时间为空
- 运行中持续落盘，程序中断后可继续

注意：
- 归集脚本、合约调用脚本、批量 write_contract 脚本要求 `wallet-csv` 必须包含 `privateKey` 列
- gas 归集是扣除 gas 后归集剩余可转余额
- ERC20 归集是归集 token 全部余额，但每个分发钱包仍需有足够 gas 作为手续费
- Bitget swap 中 `amount` 是人类可读数量，不是 wei
- OKX 相关脚本需要环境变量：`OKX_API_KEY`、`OKX_SECRET_KEY`、`OKX_PASSPHRASE`
