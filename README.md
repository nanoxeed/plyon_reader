# plyon-reader

tacterion の接触センサ **plyon stretch** のスライダー値を読み取り、接触位置と押し込み値をリアルタイム表示する Python スクリプトです。

## セットアップ

Python 3.14 以上と uv が必要です。可視化には `tkinter` と GUI 環境を使用します。

```bash
uv sync
```

## 使い方

```bash
# 接触位置を可視化
uv run python read_slider.py --visualize --port /dev/ttyACM0

# 生データを端末に表示
uv run python read_slider.py --port /dev/ttyACM0

# 実機なしでデモを表示
uv run python read_slider.py --demo --quiet
```

既定の通信速度は `115200` baud。Windows では `--port COM3` のように指定します。
ウィンドウを閉じるか、端末で Ctrl+C を押すと終了します。

接触判定は既定で押し込み値が `20` を超えた場合です。`--force-threshold` で調整し、`--reverse` で左右反転できます。
その他の設定は `uv run python read_slider.py --help` を参照してください。

## 入力データ

既定では8列CSVの7列目を位置、8列目を押し込み値として読み取ります。

```text
0000,0000,0000,0000,0000,0000,2048,0800
```

位置は `0..4095` を `0..100%` に換算します。押し込み値は未校正の生値で、N 単位ではありません。
D02 の取得ログと模擬シリアル入力で確認済みです。実機への直接接続と位置校正は未検証です。
