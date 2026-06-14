package com.example.eval;

import com.example.eval.adapters.InMemoryAccountRepository;
import com.example.eval.application.AccountRepository;
import com.example.eval.domain.Account;
import com.example.eval.domain.Money;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Baseline smoke test — passes on the untouched seed project. Golden-task
 * overlays add their own tests; the agent must keep this one green too.
 */
class SmokeTest {

    @Test
    void depositIncreasesBalanceAndPersists() {
        AccountRepository repo = new InMemoryAccountRepository();
        Account acct = new Account("acct-1", Money.ofCents(1000));
        acct.deposit(Money.ofCents(500));
        repo.save(acct);

        assertEquals(1500, repo.findById("acct-1").orElseThrow().balance().cents());
        assertTrue(repo.findById("missing").isEmpty());
    }
}
