package com.example.eval;

import com.example.eval.domain.Account;
import com.example.eval.domain.Money;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

/** Acceptance oracle for the `account-withdraw` task. */
class AccountWithdrawTest {

    @Test
    void withdrawReducesBalance() {
        Account a = new Account("a", Money.ofCents(1000));
        a.withdraw(Money.ofCents(400));
        assertEquals(600, a.balance().cents());
    }

    @Test
    void withdrawExactBalanceLeavesZero() {
        Account a = new Account("a", Money.ofCents(500));
        a.withdraw(Money.ofCents(500));
        assertEquals(0, a.balance().cents());
    }

    @Test
    void withdrawMoreThanBalanceThrowsAndDoesNotMutate() {
        Account a = new Account("a", Money.ofCents(100));
        assertThrows(IllegalStateException.class, () -> a.withdraw(Money.ofCents(101)));
        assertEquals(100, a.balance().cents(), "balance must be unchanged after a failed withdraw");
    }
}
