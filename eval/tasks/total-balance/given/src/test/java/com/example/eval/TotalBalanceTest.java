package com.example.eval;

import com.example.eval.adapters.InMemoryAccountRepository;
import com.example.eval.application.AccountRepository;
import com.example.eval.domain.Account;
import com.example.eval.domain.Money;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

/** Acceptance oracle for the `total-balance` task. Calls through the PORT type
 *  so the method must be added to the AccountRepository interface, not just the
 *  concrete adapter. */
class TotalBalanceTest {

    @Test
    void totalBalanceSumsAllAccounts() {
        AccountRepository repo = new InMemoryAccountRepository();
        repo.save(new Account("a", Money.ofCents(1000)));
        repo.save(new Account("b", Money.ofCents(2500)));
        assertEquals(3500, repo.totalBalance().cents());
    }

    @Test
    void totalBalanceOfEmptyRepositoryIsZero() {
        AccountRepository repo = new InMemoryAccountRepository();
        assertEquals(0, repo.totalBalance().cents());
    }
}
