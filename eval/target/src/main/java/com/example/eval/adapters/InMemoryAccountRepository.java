package com.example.eval.adapters;

import com.example.eval.application.AccountRepository;
import com.example.eval.domain.Account;

import java.util.Map;
import java.util.Optional;
import java.util.concurrent.ConcurrentHashMap;

/**
 * In-memory adapter for {@link AccountRepository} — the test/sandbox driver.
 */
public class InMemoryAccountRepository implements AccountRepository {

    private final Map<String, Account> store = new ConcurrentHashMap<>();

    @Override
    public void save(Account account) {
        store.put(account.id(), account);
    }

    @Override
    public Optional<Account> findById(String id) {
        return Optional.ofNullable(store.get(id));
    }
}
