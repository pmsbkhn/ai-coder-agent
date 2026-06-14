package com.example.eval.domain;

/**
 * Account aggregate root. Holds a balance and enforces its own invariants.
 *
 * Seed capabilities: open with an initial balance, deposit, read the balance.
 * Golden tasks extend this (e.g. withdraw) by making pre-written tests pass.
 */
public class Account {

    private final String id;
    private Money balance;

    public Account(String id, Money initialBalance) {
        if (initialBalance.isNegative()) {
            throw new IllegalArgumentException("initial balance cannot be negative");
        }
        this.id = id;
        this.balance = initialBalance;
    }

    public String id() {
        return id;
    }

    public Money balance() {
        return balance;
    }

    public void deposit(Money amount) {
        if (amount.isNegative()) {
            throw new IllegalArgumentException("cannot deposit a negative amount");
        }
        this.balance = this.balance.plus(amount);
    }
}
