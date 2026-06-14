package com.example.eval;

import com.example.eval.adapters.InMemoryAccountRepository;
import com.example.eval.application.AccountRepository;
import com.example.eval.application.TransferService;
import com.example.eval.domain.Account;
import com.example.eval.domain.Money;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

/** Acceptance oracle for the `transfer-service` task. */
class TransferServiceTest {

    private AccountRepository repoWith(Account... accounts) {
        AccountRepository repo = new InMemoryAccountRepository();
        for (Account a : accounts) {
            repo.save(a);
        }
        return repo;
    }

    @Test
    void transferMovesMoneyBetweenAccounts() {
        AccountRepository repo = repoWith(
                new Account("from", Money.ofCents(1000)),
                new Account("to", Money.ofCents(0)));
        new TransferService(repo).transfer("from", "to", Money.ofCents(300));

        assertEquals(700, repo.findById("from").orElseThrow().balance().cents());
        assertEquals(300, repo.findById("to").orElseThrow().balance().cents());
    }

    @Test
    void insufficientFundsThrowsAndLeavesBalancesUnchanged() {
        AccountRepository repo = repoWith(
                new Account("from", Money.ofCents(100)),
                new Account("to", Money.ofCents(50)));
        TransferService svc = new TransferService(repo);

        assertThrows(IllegalStateException.class, () -> svc.transfer("from", "to", Money.ofCents(500)));
        assertEquals(100, repo.findById("from").orElseThrow().balance().cents());
        assertEquals(50, repo.findById("to").orElseThrow().balance().cents());
    }

    @Test
    void unknownAccountThrows() {
        AccountRepository repo = repoWith(new Account("from", Money.ofCents(100)));
        TransferService svc = new TransferService(repo);
        assertThrows(IllegalArgumentException.class,
                () -> svc.transfer("from", "missing", Money.ofCents(10)));
    }
}
