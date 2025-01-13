#!/usr/bin/env python3

import time
import subprocess
import asyncio
from datetime import datetime
from collections import defaultdict
from nicegui import ui, app

CHANNELS = {
    "R1": 5658,
    "R2": 5695,
    "R3": 5732,
    "R4": 5769,
    "R5": 5806,
    "R6": 5843,
    "R7": 5880,
    "R8": 5917,
}
MHz = int(1e6)
SCAN_FROM = (CHANNELS["R1"] - 20) * MHz
SCAN_TO = (CHANNELS["R8"] + 20) * MHz
SCAN_BUCKET_WIDTH_HZ = 200000
UPDATE_PERIOD = 0.5
TIME_WINDOWS = [1]

points = range(SCAN_FROM, SCAN_TO, SCAN_BUCKET_WIDTH_HZ)

channel_marks = [
    [
        {'name': f"{chname}\n{chfreq} MHz", 'xAxis': (chfreq - 10)*MHz},
        {'xAxis': (chfreq + 10)*MHz},
    ]
    for chname, chfreq in CHANNELS.items()
]

chart = ui.echart({
    'animation': False,
    'xAxis': {
        'type': 'value',
        'min': SCAN_FROM,
        'max': SCAN_TO,
        'axisLabel': {
            ':formatter': 'value => value/1000000',
            # 'showMaxLabel': True,
            # 'showMinLabel': True,
        }
    },
    'yAxis': {
        'type': 'value',
        'min': -70,
        'max': 0,
        'axisLabel': {
            'formatter': '{value} dB',
        },
        'clip': True,
    },
    'series': [
        {
            'name': f'Max of last {tw} seconds',
            'type': 'line',
            'showSymbol': False,
            'data': [],
            'smooth': True,
            'markArea': {
                'itemStyle': {
                    'color': 'rgba(0,180,0,0.1)',
                },
                'data': channel_marks,
            },
        }
        for tw in TIME_WINDOWS
    ]
}).classes('h-[600px] w-[100%] m-2')

sweeper_proc = None

async def run_sweeper():
    global sweeper_proc
    sweeper_proc = await asyncio.create_subprocess_exec(
        "hackrf_sweep",
        "-f",
        f"{SCAN_FROM//MHz}:{SCAN_TO//MHz}",
        "-a",
        "1",
        "-w",
        str(SCAN_BUCKET_WIDTH_HZ),
        stdout=subprocess.PIPE,
    )

    data = []
    last_update = 0

    while True:
        line = await sweeper_proc.stdout.readline()
        if not line:
            break

        line = line.decode().strip().split(', ')

        dt = datetime.strptime(" ".join(line[0:2]), "%Y-%m-%d %H:%M:%S.%f")
        ts = dt.timestamp()

        fr_from, fr_to, fr_step = map(int, map(float, line[2:5]))
        for freq, db in zip(range(fr_from, fr_to, fr_step), line[6:]):
            data.append((ts, freq, float(db)))

        now = time.time()
        if now - last_update > UPDATE_PERIOD:

            series_by_time = {t: dict() for t in TIME_WINDOWS}
            for ts, freq, db in data:
                for tw in TIME_WINDOWS:
                    if now - ts <= tw:
                        old_max = series_by_time[tw].get(freq, db)
                        series_by_time[tw][freq] = max(old_max, db)

            # remove expired values
            max_ts = max(TIME_WINDOWS)
            old_len = len(data)
            data = [d for d in data if d[0] > now - max_ts]
            new_len = len(data)
            print(f"Data points: {old_len} -> {new_len}")

            for i, tw in enumerate(TIME_WINDOWS):
                sdata = sorted(series_by_time[tw].items(), 
                                key=lambda x: x[0])
                chart.options['series'][i]['data'] = sdata
            chart.update()

            last_update = now


@app.on_startup
async def start():
    asyncio.create_task(run_sweeper())

@app.on_shutdown
async def stop():
    print("Stopping sweeper...")
    sweeper_proc.terminate()
    await sweeper_proc.wait()
    print("Stopped")

ui.run(port=5050)
