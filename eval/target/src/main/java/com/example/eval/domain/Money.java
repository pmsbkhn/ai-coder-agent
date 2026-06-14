package com.example.eval.domain;

/**
 * Immutable value object: an amount of money in whole cents. Pure domain — no
 * framework, no persistence concerns.
 */
public final class Money {

    private final long cents;

    private Money(long cents) {
        this.cents = cents;
    }

    public static Money ofCents(long cents) {
        return new Money(cents);
    }

    public static Money zero() {
        return new Money(0);
    }

    public long cents() {
        return cents;
    }

    public Money plus(Money other) {
        return new Money(this.cents + other.cents);
    }

    public Money minus(Money other) {
        return new Money(this.cents - other.cents);
    }

    public boolean isNegative() {
        return cents < 0;
    }

    public boolean isLessThan(Money other) {
        return this.cents < other.cents;
    }

    @Override
    public boolean equals(Object o) {
        return (o instanceof Money m) && m.cents == this.cents;
    }

    @Override
    public int hashCode() {
        return Long.hashCode(cents);
    }

    @Override
    public String toString() {
        return "Money{" + cents + "c}";
    }
}
