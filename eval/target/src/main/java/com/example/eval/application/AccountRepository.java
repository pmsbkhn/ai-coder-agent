package com.example.eval.application;

import com.example.eval.domain.Account;

import java.util.Optional;

/**
 * Outbound port: persistence for {@link Account} aggregates. The domain depends
 * on this interface; adapters implement it (hexagonal / ports & adapters).
 */
public interface AccountRepository {

    void save(Account account);

    Optional<Account> findById(String id);
}
