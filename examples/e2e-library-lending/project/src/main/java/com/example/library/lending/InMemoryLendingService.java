package com.example.library.lending;

import com.example.library.catalog.CatalogService;
import com.example.library.membership.MemberService;
import java.time.LocalDate;
import java.util.Map;
import java.util.HashMap;
import java.util.UUID;

public class InMemoryLendingService extends LendingService {
    private final Map<String, Loan> loans;

    public InMemoryLendingService(CatalogService catalog, MemberService members) {
        super(catalog, members);
        this.loans = new HashMap<>();
    }

    @Override
    public Loan createLoan(String memberId, String copyId, LocalDate dueDate) {
        Loan loan = super.createLoan(memberId, copyId, dueDate); // builds the Loan
        loans.put(loan.getId(), loan);                         // keep the same instance
        return loan;
    }

    @Override
    public boolean isOverdue(String loanId, LocalDate today) {
        Loan loan = loans.get(loanId);
        if (loan == null) {
            throw new IllegalArgumentException("Loan not found: " + loanId);
        }
        return loan.isOverdue(today);
    }

    @Override
    public void returnLoan(String loanId, LocalDate returnDate) {
        Loan loan = loans.get(loanId);
        if (loan == null) {
            throw new IllegalArgumentException("Loan not found: " + loanId);
        }
        loan.returnLoanInPlace(returnDate);
    }

    public void addLoan(Loan loan) {
        loans.put(loan.getId(), loan);
    }

    public Loan getLoan(String loanId) {
        return loans.get(loanId);
    }
}