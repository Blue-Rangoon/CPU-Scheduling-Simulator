import os
import random
import tempfile
import unittest

import data_io
from scheduler_engine import (ALGOS, ProcessInput, SchedOptions, process_colors, run_algorithm, run_all)


def sample():
    return [ProcessInput("P1", 0, 5, 2, 0, 12), ProcessInput("P2", 1, 3, 1, 0, 6),
            ProcessInput("P3", 2, 8, 4, 1, 30), ProcessInput("P4", 3, 6, 3, 1, 20)]


def ct(out):
    return {r.pid: r.ct for r in out.results}


class TestExactResults(unittest.TestCase):
    def test_fcfs(self):
        o = run_algorithm("FCFS", sample())
        self.assertEqual(ct(o), {"P1": 5, "P2": 8, "P3": 16, "P4": 22})
        self.assertEqual(o.avg_wt, 5.75)

    def test_sjf(self):
        self.assertEqual(ct(run_algorithm("SJF", sample())), {"P1": 5, "P2": 8, "P3": 22, "P4": 14})

    def test_srtf(self):
        o = run_algorithm("SRTF", sample())
        self.assertEqual(ct(o), {"P1": 8, "P2": 4, "P3": 22, "P4": 14})
        self.assertEqual(o.avg_wt, 5.0)

    def test_ljf(self):
        self.assertEqual(ct(run_algorithm("LJF", sample())), {"P1": 5, "P2": 22, "P3": 13, "P4": 19})

    def test_round_robin(self):
        o = run_algorithm("RR", sample(), SchedOptions(quantum=2))
        self.assertEqual(ct(o), {"P1": 14, "P2": 11, "P3": 22, "P4": 20})

    def test_priority_preemptive(self):
        o = run_algorithm("PRIO_P", sample())
        self.assertEqual(ct(o)["P2"], 4)

    def test_priority_high_number(self):
        o = run_algorithm("PRIO_NP", sample(), SchedOptions(high_is_priority=True))
        self.assertEqual([g.pid for g in o.gantt], ["P1", "P3", "P4", "P2"])

    def test_idle_gap(self):
        o = run_algorithm("FCFS", [ProcessInput("A", 3, 2)])
        self.assertEqual(o.gantt[0].kind, "idle")
        self.assertEqual(o.end_time, 5)

    def test_context_switch(self):
        o = run_algorithm("FCFS", sample(), SchedOptions(cs_time=1))
        self.assertEqual(o.cs_count, 3)
        self.assertEqual(o.end_time, 25)

    def test_aging_prevents_starvation(self):
        procs = [ProcessInput("L", 0, 3, 9)] + [ProcessInput(f"H{i}", i, 3, 1) for i in range(1, 6)]
        no_age = run_algorithm("PRIO_NP", procs)
        aged = run_algorithm("PRIO_NP", procs, SchedOptions(aging=2))
        self.assertLessEqual(aged.results[0].ct, no_age.results[0].ct)

    def test_edf_deadlines(self):
        o = run_algorithm("EDF", sample())
        self.assertTrue(all(r.deadline_met for r in o.results if r.pid in ("P1", "P2")))

    def test_mlq_higher_queue_first(self):
        o = run_algorithm("MLQ", sample())
        done = ct(o)
        self.assertLess(done["P2"], done["P3"])

    def test_lottery_reproducible(self):
        a = run_algorithm("LOTTERY", sample(), SchedOptions(seed=7))
        b = run_algorithm("LOTTERY", sample(), SchedOptions(seed=7))
        self.assertEqual([(g.pid, g.start) for g in a.gantt], [(g.pid, g.start) for g in b.gantt])


class TestInvariants(unittest.TestCase):
    """Properties every algorithm must satisfy on random inputs."""

    def test_random_sets(self):
        rng = random.Random(42)
        for _ in range(40):
            n = rng.randint(1, 8)
            procs = [ProcessInput(f"P{i + 1}", rng.randint(0, 12), rng.randint(1, 9), rng.randint(1, 5),
                                  rng.randint(0, 2), rng.randint(5, 40)) for i in range(n)]
            opts = SchedOptions(quantum=rng.choice([1, 2, 3]), cs_time=rng.choice([0, 0, 1]))
            for key, out in run_all(procs, opts).items():
                ran = {}
                for g in out.raw_gantt:
                    self.assertLess(g.start, g.end)
                    if g.kind == "run":
                        ran[g.pid] = ran.get(g.pid, 0) + g.end - g.start
                prev = 0
                for g in out.gantt:                       # no overlaps, continuous timeline
                    self.assertAlmostEqual(g.start, prev, places=4, msg=key)
                    prev = g.end
                for r in out.results:
                    self.assertAlmostEqual(ran[r.pid], r.bt, places=4, msg=f"{key} {r.pid}")
                    self.assertAlmostEqual(r.tat, r.wt + r.bt, places=2, msg=key)
                    self.assertGreaterEqual(r.first_start, r.at - 1e-9, msg=key)
                    self.assertGreaterEqual(r.wt, -1e-9, msg=key)
                self.assertTrue(out.steps and out.summary)


class TestIO(unittest.TestCase):
    def test_excel_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "t.xlsx")
            data_io.write_template(p)
            procs = data_io.import_processes(p)
            self.assertEqual(len(procs), 5)
            out = run_algorithm("RR", procs)
            colors = process_colors("RR", [x.pid for x in procs])
            data_io.export_excel(os.path.join(d, "o.xlsx"), out, procs, colors, run_all(procs))
            data_io.export_csv(os.path.join(d, "o.csv"), out)
            data_io.export_gantt_png(os.path.join(d, "g.png"), out, colors)
            for f in ("o.xlsx", "o.csv", "g.png"):
                self.assertTrue(os.path.getsize(os.path.join(d, f)) > 0)

    def test_bad_excel(self):
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "bad.csv")
            with open(p, "w") as f:
                f.write("PID,Arrival Time,Burst Time\nP1,0,0\n")
            with self.assertRaises(ValueError):
                data_io.import_processes(p)

    def test_all_algorithms_registered(self):
        self.assertEqual(len(ALGOS), 15)


if __name__ == "__main__":
    unittest.main()
