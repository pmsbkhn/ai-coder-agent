package com.example.library.common;

public class DomainException extends RuntimeException {
    private final Code code;

    public DomainException(Code code, String message) {
        super(message);
        this.code = code;
    }

    public Code getCode() {
        return code;
    }

    public enum Code {
        BORROW_LIMIT_EXCEEDED,
        COPY_NOT_AVAILABLE,
        MEMBER_SUSPENDED,
        LOAN_ALREADY_RETURNED
    }
}