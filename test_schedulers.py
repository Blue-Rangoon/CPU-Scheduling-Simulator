import unittest

from scheduler_engine import (
    ProcessInput,
    _fmt,
    run_fcfs,
    run_hrrn,
    run_multilevel_queue,
    run_priority_non_preemptive,
    run_priority_preemptive,
    run_round_robin,
    run_sjf_non_preemptive,
    run_srtf_preemptive,
)


def sample_processes():
    return [
        ProcessInput("P1", 0, 5, priority=2, queue_level=0),
        ProcessInput("P2", 1, 3, priority=1, queue_level=0),
        ProcessInput("P3", 2, 8, priority=4, queue_level=1),
        ProcessInput("P4", 3, 6, priority=3, queue_level=1),
    ]


def by_pid(results):
    return {r.pid: r for r in results}


class TestNotebookSchedulerEngine(unittest.TestCase):
    def assert_formulas(self, out):
        for r in out.results:
            self.assertAlmostEqual(r.tat, round(r.ct - r.at, 2))
            self.assertAlmostEqual(r.wt, round(r.tat - r.bt, 2))
            self.assertGreaterEqual(r.rt, 0.0)
        self.assertTrue(len(out.iteration_logs) >= 1)

    def test_fcfs_idle_and_fractional_cs(self):
        procs = [ProcessInput("P1", 2, 3), ProcessInput("P2", 3, 2)]
        out = run_fcfs(procs, cs_enabled=True, cs_time=0.4)
        self.assert_formulas(out)

        self.assertTrue(out.gantt[0].is_idle)
        self.assertEqual((out.gantt[0].start, out.gantt[0].end), (0.0, 2.0))
        self.assertFalse(out.gantt[1].cs_before)
        self.assertTrue(out.gantt[2].cs_before)
        self.assertEqual(out.context_switch_count, 1)
        self.assertEqual(out.context_switch_points, [5.0])
        self.assertAlmostEqual(out.total_cs_overhead, 0.4)

        m = by_pid(out.results)
        self.assertAlmostEqual(m["P1"].ct, 5.0)
        self.assertAlmostEqual(m["P2"].ct, 7.4)
        self.assertAlmostEqual(m["P2"].rt, 2.4)
        self.assertEqual(_fmt(m["P2"].ct), "7.4")

    def test_sjf_and_srtf(self):
        sjf_out = run_sjf_non_preemptive(sample_processes())
        self.assert_formulas(sjf_out)
        self.assertAlmostEqual(sjf_out.avg_tat, 10.75)
        self.assertAlmostEqual(sjf_out.avg_wt, 5.25)
        self.assertAlmostEqual(sjf_out.avg_rt, 5.25)
        self.assertAlmostEqual(sjf_out.avg_bt, 5.5)
        self.assertAlmostEqual(sjf_out.cpu_utilization, 100.0)

        srtf_out = run_srtf_preemptive(sample_processes())
        self.assert_formulas(srtf_out)
        m = by_pid(srtf_out.results)
        self.assertAlmostEqual(m["P1"].ct, 8.0)
        self.assertAlmostEqual(m["P2"].ct, 4.0)
        self.assertAlmostEqual(m["P4"].ct, 14.0)
        self.assertAlmostEqual(m["P3"].ct, 22.0)
        self.assertAlmostEqual(srtf_out.avg_tat, 10.5)
        self.assertAlmostEqual(srtf_out.avg_wt, 5.0)
        self.assertAlmostEqual(srtf_out.avg_rt, 4.25)

    def test_priority_non_preemptive_and_preemptive_with_aging(self):
        # Verify Aging = floor(WT / interval) and Effective = max(0, IP - Aging)
        procs = [
            ProcessInput("P1", 0, 4, priority=1),
            ProcessInput("P2", 0, 1, priority=4),
            ProcessInput("P3", 2, 4, priority=1),
            ProcessInput("P4", 4, 2, priority=1),
        ]
        no_age = run_priority_non_preemptive(procs, aging_enabled=False)
        with_age = run_priority_non_preemptive(
            procs, aging_enabled=True, aging_interval=2.0
        )
        self.assert_formulas(no_age)
        self.assert_formulas(with_age)
        self.assertGreater(
            by_pid(no_age.results)["P2"].ct, by_pid(with_age.results)["P2"].ct
        )
        for r in with_age.results:
            self.assertGreaterEqual(r.final_priority, 0)

        pre_out = run_priority_preemptive(
            [ProcessInput("P1", 0, 4, priority=3), ProcessInput("P2", 1, 2, priority=1)],
            aging_enabled=True,
            aging_interval=3.0,
        )
        self.assert_formulas(pre_out)
        pm = by_pid(pre_out.results)
        self.assertAlmostEqual(pm["P2"].ct, 3.0)
        self.assertAlmostEqual(pm["P1"].ct, 6.0)
        self.assertAlmostEqual(pm["P1"].rt, 0.0)

    def test_round_robin_and_hrrn(self):
        rr_out = run_round_robin(sample_processes(), quantum=2.0)
        self.assert_formulas(rr_out)
        self.assertAlmostEqual(rr_out.avg_tat, 15.25)
        self.assertAlmostEqual(rr_out.avg_wt, 9.75)
        self.assertAlmostEqual(rr_out.avg_rt, 2.0)

        hrrn_out = run_hrrn(sample_processes())
        self.assert_formulas(hrrn_out)
        self.assertAlmostEqual(hrrn_out.avg_tat, 10.75)
        self.assertAlmostEqual(hrrn_out.avg_wt, 5.25)

    def test_multilevel_queue_q0_rr_rotation_and_q1_preemption(self):
        procs = [
            ProcessInput("P1", 0, 4, queue_level=0),
            ProcessInput("P2", 0, 4, queue_level=0),
            ProcessInput("P3", 1, 3, queue_level=1),
        ]
        out = run_multilevel_queue(
            procs, q0_policy="RR", q0_quantum=2.0, q1_policy="FCFS"
        )
        self.assert_formulas(out)
        # Q0 must rotate P1 [0,2], P2 [2,4], P1 [4,6], P2 [6,8], then P3 [8,11]
        seq = [(s.pid, s.start, s.end) for s in out.gantt]
        self.assertEqual(
            seq,
            [
                ("P1", 0.0, 2.0),
                ("P2", 2.0, 4.0),
                ("P1", 4.0, 6.0),
                ("P2", 6.0, 8.0),
                ("P3", 8.0, 11.0),
            ],
        )


if __name__ == "__main__":
    unittest.main()
