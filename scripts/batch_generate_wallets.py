from web3 import Web3
import datetime
import csv
import argparse
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description="批量生成钱包并导出 CSV")
    parser.add_argument("--project", required=True, help="项目名，例如 op")
    parser.add_argument("--count", required=True, type=int, help="钱包数量，1-n")
    parser.add_argument("--rpc", default="https://bsc-dataseed.binance.org/", help="RPC 地址")
    args = parser.parse_args()

    if args.count < 1:
        raise ValueError("count 必须 >= 1")

    # Initialize Web3 connection
    web3 = Web3(Web3.HTTPProvider(args.rpc))
    print(web3.is_connected())

    # Number of wallets to generate
    num_wallets = args.count

    # Generate wallets and collect their information
    wallet_info = []
    for index in range(1, num_wallets + 1):
        newAccount = web3.eth.account.create()
        wallet_info.append([index, newAccount.address, newAccount._private_key.hex()])

    # Create a timestamped file name
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    wallet_dir = Path("output/wallet").resolve()
    wallet_dir.mkdir(parents=True, exist_ok=True)
    file_name = wallet_dir / f"wallet_{timestamp}-{args.project}-{num_wallets}.csv"

    # Save wallet information to the CSV file
    with file_name.open("w", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(["序号", "address", "privateKey"])  # Write the header
        writer.writerows(wallet_info)  # Write the wallet data

    print(f"Wallet information saved to {file_name}")


if __name__ == "__main__":
    main()
