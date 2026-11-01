"""Я проверяю бизнес-примеры и файловые гарантии независимыми ожиданиями."""
from contextlib import closing
import csv
from datetime import date
import json
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch

from settlement import contracts
from settlement.contracts import ContractError, ORDER_FIELDS, PAYMENT_FIELDS, load
from settlement.engine import calculate, connect, inspect, run
from settlement.examples import data, write_csv


class SettlementTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.orders, self.payments = data()
        self.save()

    def save(self):
        self.op, self.pp = self.base / 'orders.csv', self.base / 'payments.csv'
        for path, fields, rows in [(self.op, ORDER_FIELDS, self.orders), (self.pp, PAYMENT_FIELDS, self.payments)]:
            path.unlink(missing_ok=True)
            write_csv(path, fields, rows)

    def calc(self, tolerance=0, as_of='2026-11-01'):
        return calculate(self.op, self.pp, as_of, tolerance)

    def test_demo_statuses_and_separate_currencies(self):
        rows, summary = self.calc()
        self.assertEqual(summary['statuses'], dict(matched=2, missing_payment=2, underpaid=2, overpaid=1, orphan_payment=2))
        self.assertEqual((len(rows), summary['issues']), (9, 7))
        self.assertEqual([(r['currency'], r['expected_minor'], r['net_minor'], r['delta_minor']) for r in summary['by_currency']], [('RUB', 26001, 15200, -10801), ('USD', 2000, 9500, 7500)])

    def test_split_payment_does_not_multiply_order(self):
        row = next(r for r in self.calc()[0] if r['order_id'] == 'O100')
        self.assertEqual((row['expected_minor'], row['payment_count'], row['net_minor']), (10000, 2, 10000))

    def test_exact_duplicate_is_applied_once(self):
        rows, summary = self.calc()
        self.assertEqual(summary['input']['payment_duplicates'], 1)
        self.payments.pop(2)
        self.save()
        self.assertEqual(self.calc()[0], rows)

    def test_conflicting_payment_even_in_future_rejected(self):
        self.payments.append(('P2', 'O100', 'RUB', 4001, 'capture', '2026-11-02'))
        self.save()
        with self.assertRaisesRegex(ContractError, 'конфликт'):
            self.calc()

    def test_duplicate_order_even_identical_rejected(self):
        self.orders.append(self.orders[0])
        self.save()
        with self.assertRaises(ContractError): self.calc()

    def test_refund_subtracts_from_capture(self):
        row = next(r for r in self.calc()[0] if r['order_id'] == 'O200')
        self.assertEqual((row['captured_minor'], row['refunded_minor'], row['net_minor'], row['delta_minor']), (5000, 1000, 4000, -1000))

    def test_currency_mismatch_remains_two_issues(self):
        rows = [r for r in self.calc()[0] if r['order_id'] == 'O500']
        self.assertEqual([(r['currency'], r['status']) for r in rows], [('RUB', 'missing_payment'), ('USD', 'orphan_payment')])

    def test_zero_order_without_payment_is_matched(self):
        row = next(r for r in self.calc()[0] if r['order_id'] == 'O600')
        self.assertEqual((row['payment_count'], row['status']), (0, 'matched'))

    def test_tolerance_boundary_preserves_delta(self):
        row = next(r for r in self.calc(1)[0] if r['order_id'] == 'O700')
        self.assertEqual((row['delta_minor'], row['status']), (-1, 'matched'))
        self.assertEqual(self.calc(1)[1]['issues'], 6)
        self.assertEqual(self.calc(0)[1]['issues'], 7)

    def test_tolerance_does_not_hide_absence(self):
        rows, _ = self.calc(10**9)
        self.assertEqual(sum(r['status'] == 'missing_payment' for r in rows), 2)
        self.assertEqual(sum(r['status'] == 'orphan_payment' for r in rows), 2)

    def test_as_of_is_inclusive_and_future_is_counted(self):
        self.assertEqual(self.calc()[1]['excluded_future'], {'orders': 1, 'payments': 1})
        rows, summary = self.calc(as_of='2026-11-02')
        self.assertEqual((len(rows), summary['issues']), (10, 7))
        self.assertEqual(next(r for r in rows if r['order_id'] == 'O400')['status'], 'matched')
        self.assertEqual(self.calc(as_of='2026-10-31')[0], [])

    def test_negative_net_and_zero_orphan_keep_presence(self):
        self.orders = []
        self.payments = [('R1','ORPHAN','EUR',10,'refund','2026-11-01'), ('C1','ZERO','EUR',5,'capture','2026-11-01'), ('R2','ZERO','EUR',5,'refund','2026-11-01')]
        self.save()
        rows, _ = self.calc()
        self.assertEqual([(r['net_minor'],r['status']) for r in rows], [(-10,'orphan_payment'), (0,'orphan_payment')])

    def test_shuffled_input_matches_independent_python_oracle(self):
        # Я строю ожидаемые числа простым словарём, без копирования SQL CASE/CTE.
        rng = random.Random(17)
        self.orders = [(f'O{i}', 'EUR', rng.randrange(0, 10000), '2026-11-01') for i in range(70)]
        self.payments = [(f'P{i}', f'O{rng.randrange(0,90)}', 'EUR', rng.randrange(1,2000), rng.choice(['capture','refund']), '2026-11-01') for i in range(200)]
        expected = {o[0]: [o[2], 0, 0] for o in self.orders}
        for _, oid, _, value, kind, _ in self.payments:
            acc = expected.setdefault(oid, [0, 0, 0])
            acc[1 if kind == 'capture' else 2] += value
        rng.shuffle(self.orders); rng.shuffle(self.payments)
        self.save()
        rows, _ = self.calc()
        actual = {r['order_id']: [r['expected_minor'],r['captured_minor'],r['refunded_minor']] for r in rows}
        self.assertEqual(actual, expected)
        self.assertTrue(all(r['delta_minor'] == expected[r['order_id']][1] - expected[r['order_id']][2] - expected[r['order_id']][0] for r in rows))

    def test_invalid_contract_cases(self):
        for value in ['-1', '1.1', '01', ' 4', '1000000000001']:
            with self.subTest(value=value), self.assertRaises(ContractError): contracts.amount(value, zero=True)
        for value in ['2026-02-30', '20261101', '2026-1-01']:
            with self.subTest(value=value), self.assertRaises(ContractError): contracts.iso_day(value)
        for value in ['rub', 'EURO', 'R1B']:
            with self.subTest(value=value), self.assertRaises(ContractError): contracts.currency(value)
        for value in [-1, 10**9+1, True]:
            with self.subTest(value=value), self.assertRaises(ContractError): self.calc(value)

    def test_bad_csv_header_width_and_utf8(self):
        for raw in [b'wrong\n', b'order_id,currency,expected_minor,ordered_on\nO1,RUB,1\n', b'\xff']:
            self.op.write_bytes(raw)
            with self.subTest(raw=raw), self.assertRaises(ContractError): self.calc()

    def test_resource_limits(self):
        with patch.object(contracts, 'MAX_BYTES', 20), self.assertRaises(ContractError): self.calc()
        with patch.object(contracts, 'MAX_ROWS', 2), self.assertRaises(ContractError): self.calc()

    def test_large_exact_integers_and_empty_typed_parquet(self):
        self.orders = [('BIG','RUB',10**12,'2026-11-01')]
        self.payments = [('P1','BIG','RUB',10**12-1,'capture','2026-11-01')]
        self.save()
        self.assertEqual(self.calc()[0][0]['delta_minor'], -1)
        out = self.base / 'empty'
        run(self.op,self.pp,out,'2026-10-31')
        self.assertEqual(inspect(out)['preview'], [])
        with closing(connect()) as con:
            fields = con.execute('DESCRIBE SELECT * FROM read_parquet(?)', [str(out/'reconciliation.parquet')]).fetchall()
        self.assertIn(('delta_minor','BIGINT'), [(r[0],r[1]) for r in fields])

    def test_publish_replay_refusal_and_corruption(self):
        a,b = self.base/'a', self.base/'b'
        run(self.op,self.pp,a,'2026-11-01'); run(self.op,self.pp,b,'2026-11-01')
        self.assertEqual(inspect(a), inspect(b))
        before = {p.name:p.read_bytes() for p in a.iterdir()}
        with self.assertRaises(FileExistsError): run(self.op,self.pp,a,'2026-11-01')
        self.assertEqual(before, {p.name:p.read_bytes() for p in a.iterdir()})
        with (a/'reconciliation.csv').open('ab') as f:f.write(b'corruption')
        with self.assertRaisesRegex(ContractError, 'повреждение'): inspect(a)

    def test_failure_cleans_stage_and_lock(self):
        out = self.base/'failure'
        with self.assertRaisesRegex(RuntimeError, 'failpoint'):
            run(self.op,self.pp,out,'2026-11-01',fail_before_publish=True)
        self.assertFalse(out.exists())
        self.assertFalse(list(self.base.glob('.settlement-stage-*')))
        self.assertFalse(out.with_suffix('.lock').exists())
        self.assertEqual(run(self.op,self.pp,out,'2026-11-01')['issues'], 7)

    def test_existing_lock_is_preserved(self):
        lock = self.base/'busy.lock'; lock.write_text('other writer')
        with self.assertRaises(FileExistsError): run(self.op,self.pp,self.base/'busy','2026-11-01')
        self.assertEqual(lock.read_text(), 'other writer')


if __name__ == '__main__': unittest.main()
