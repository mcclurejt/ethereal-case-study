import asyncio
import os
import pandas as pd
import requests
import time
import datetime
import matplotlib.pyplot as plt
from driftpy.clearing_house import ClearingHouse
from driftpy.clearing_house_user import ClearingHouseUser
from driftpy.constants.config import CONFIG
from driftpy.constants.markets import MARKETS
from driftpy.types import TradeDirection, PositionDirection
from spl.token.instructions import get_associated_token_address
from solana.publickey import PublicKey

os.environ['ANCHOR_WALLET'] = os.path.expanduser('~/.config/solana/id.json')
ENV = 'mainnet'


async def drift():
    # create account
    drift_acct = await ClearingHouse.create_from_env(ENV)

    # load market data
    markets = (await drift_acct.get_markets_account()).markets

    # generate a market summary df
    markets_summary = pd.concat([
        pd.DataFrame(MARKETS).iloc[:, :3],
        pd.DataFrame(markets),
        pd.DataFrame([x.amm for x in markets]),
    ], axis=1).dropna(subset=['symbol'])
    markets_summary["market_index"] = markets_summary["market_index"].astype(
        int)
    print(markets_summary.columns)
    print(markets_summary)

    # generate a trade history df
    th = await drift_acct.get_trade_history_account()
    trade_history = pd.DataFrame(th.trade_records)
    trade_history.ts = pd.to_datetime(trade_history.ts, unit='s')
    trade_history = trade_history.sort_values(by='ts', ascending=True)
    trade_history.direction = pd.Series(["long" if type(
        t.direction).__name__ == "Long" else "short" for t in th.trade_records])
    print(trade_history.columns)
    print(trade_history)

    # generate a funding rate history df
    frh = await drift_acct.get_funding_rate_history_account()
    funding_rate_history = pd.DataFrame(frh.funding_rate_records)
    funding_rate_history.ts = pd.to_datetime(funding_rate_history.ts, unit='s')
    print(funding_rate_history.columns)
    print(funding_rate_history)

    # graph long-short ratio
    long_short = markets_summary
    long_short["ratio"] = long_short.apply(lambda x: abs(
        x["base_asset_amount_long"])/abs(x["base_asset_amount_short"]), axis=1)
    long_short.plot.bar(title="Long/Short Ratio", x="symbol",
                        y="ratio")
    plt.gcf().tight_layout()
    plt.gcf().savefig("../images/long_short_ratio.png")

    # graph fees collected over time
    trade_history["cumulative fees"] = trade_history.fee.cumsum()
    trade_history["cumulative fees"] = trade_history["cumulative fees"].apply(
        lambda x: x/(10**6))  # usdc uses 6 decimals
    trade_history["cumulative fee delta"] = trade_history["cumulative fees"].diff()
    trade_history.plot(title="Cumulative Fees Generated",
                       x="ts", y="cumulative fees", kind="line")
    plt.gcf().tight_layout()
    plt.gcf().savefig("../images/cumulative_fees_generated.png")

    trade_history.plot(title="Cumulative Fee Delta", x="ts",
                       y="cumulative fee delta", kind="line")
    plt.gcf().tight_layout()
    plt.gcf().savefig("../images/cumulative_fees_delta.png")

    # graph fee breakdown by market
    fee_breakdown = pd.DataFrame(markets_summary[["symbol", "market_index"]])
    fee_sum = trade_history.groupby('market_index')['fee'].sum()
    fee_breakdown = pd.merge(fee_breakdown, fee_sum,
                             how="inner", on="market_index")
    fee_breakdown["fee"] = fee_breakdown["fee"].apply(
        lambda x: x/(10**6))  # usdc uses 6 decimals
    print(fee_breakdown)
    fee_breakdown.plot.bar(title="Fees By Market", x="symbol", y="fee", rot=0)
    plt.xticks(rotation=45)
    plt.gcf().tight_layout()
    plt.gcf().savefig("../images/fees_by_market.png")

    # graph funding rates for each market over time
    grouped_funding_rates = pd.merge(funding_rate_history, markets_summary[["symbol", "market_index"]],
                                     how="inner", on="market_index")
    grouped_funding_rates["calc_funding_rate"] = grouped_funding_rates.apply(lambda row: 100*(
        1/24)*(row["mark_price_twap"]-row["oracle_price_twap"])/row["oracle_price_twap"], axis=1)
    grouped_funding_rates = grouped_funding_rates.pivot(
        index="ts", columns="symbol", values="calc_funding_rate")

    fig, ax = plt.subplots(nrows=4, ncols=4, sharex=True, sharey=True)
    fig.suptitle("Funding Rates by Market")
    r = 0
    c = 0
    for col in grouped_funding_rates.columns:
        plot_data = grouped_funding_rates[col].dropna()
        plot_data.plot(ax=ax[r, c], title=col)
        r += 1
        if r == 4:
            r = 0
            c += 1

    plt.subplots_adjust(wspace=0.2, hspace=0.2)
    fig.savefig("../images/funding_rates_by_market.png")
    plt.show()

    await drift_acct.program.close()


async def indexing():
    startDate = int(time.mktime(
        datetime.datetime(2022, 3, 20).timetuple()))
    endDate = int(time.mktime(datetime.datetime(
        2022, 3, 21).timetuple()))

    orcaAccount = 'JU8kmKzDHF9sXWsnoznaFDFezLsE5uomX2JkRMbmsQP'
    generate_transaction_csv(startDate, endDate, orcaAccount, "orca")

    raydiumAccount = 'F8Vyqk3unwxkXukZFQeYyGmFfTG3CAX4v24iyrjEYBJV'
    generate_transaction_csv(startDate, endDate, raydiumAccount, "raydium")


def generate_transaction_csv(startDate, endDate, account, name):
    print(f"Starting {name}...")
    print(f"StartDate: {startDate}")
    print(f"EndDate: {endDate}")
    params = {
        "account": account,
        "fromTime": int(startDate),
        "toTime": int(endDate),
        "limit": 50,
        "offset": 0
    }
    data = []
    while True:
        r = requests.get(
            "https://public-api.solscan.io/account/splTransfers", params=params)
        if r.status_code == 429:
            print('waiting...')
            time.sleep(31)
            print('done waiting.')
            continue
        elif r.status_code == 200:
            rdata = r.json()['data']
            if len(rdata) == 0:
                break
            data.extend(rdata)
            params["offset"] += params["limit"]
            if params["offset"] % 250 == 0:
                print(f"recorded {params['offset']} tx's")
        else:
            print("unknown error")
            break
    data = list(map(lambda x: {
                'address': x['address'],
                'changeType': x['changeType'],
                'changeAmount': x['changeAmount'],
                'decimals': x['decimals'],
                'symbol': x['symbol'],
                'blockTime': x['blockTime'],
                'tokenAddress': x['tokenAddress'],
                '_id': x['_id']
                }, data))
    df = pd.DataFrame.from_records(data)
    df.to_csv(f"{name}.csv")
    print(f"Finished recording {len(data)} tx's for {name}")
    print()


def visualization():
    orca_df = pd.read_csv('./orca.csv')
    raydium_df = pd.read_csv('./raydium.csv')


asyncio.run(drift())
