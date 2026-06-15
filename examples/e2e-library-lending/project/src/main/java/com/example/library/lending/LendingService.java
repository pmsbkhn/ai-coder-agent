package com.example.library.lending;

import com.example.library.catalog.Copy;
import com.example.library.catalog.CopyStatus;
import com.example.library.catalog.CatalogService;
import com.example.library.common.DomainException;
import com.example.library.membership.Member;
import com.example.library.membership.MemberService;
import com.example.library.membership.MemberStatus;
import java.time.LocalDate;
import java.util.Objects;

public class LendingService {
    private final CatalogService catalog;
    private final MemberService members;

    public LendingService(CatalogService catalog, MemberService members) {
        this.catalog = Objects.requireNonNull(catalog);
        this.members = Objects.requireNonNull(members);
    }

    public Loan borrowCopy(Member member, Copy copy, LocalDate dueDate) {
        // Validate member is not suspended
        if (member.getStatus() == MemberStatus.SUSPENDED) {
            throw new DomainException(DomainException.Code.MEMBER_SUSPENDED, "Member is suspended");
        }

        // Validate copy is available
        if (copy.getStatus() != CopyStatus.AVAILABLE) {
            throw new DomainException(DomainException.Code.COPY_NOT_AVAILABLE, "Copy is not available for loan");
        }

        // Increment member's loan count
        member.incrementLoanCount();

        // Loan the copy
        copy.loan();

        // Create and return the loan
        String loanId = java.util.UUID.randomUUID().toString();
        return new Loan(loanId, member.getId(), copy.getId(), LocalDate.now(), dueDate);
    }

    public void returnLoan(Loan loan) {
        if (loan.getState() == LoanState.RETURNED) {
            throw new DomainException(DomainException.Code.LOAN_ALREADY_RETURNED, "Loan already returned");
        }

        // Get the copy and member involved in this loan
        Copy copy = catalog.findCopy(loan.getCopyId());
        Member member = members.findMember(loan.getMemberId());

        // Return the copy
        copy.returnCopy();

        // Decrement member's loan count
        member.decrementLoanCount();
    }

    // used by the tests that work with IDs instead of domain objects
    public Loan createLoan(String memberId, String copyId, LocalDate dueDate) {
        Member member = members.findMember(memberId);
        Copy   copy   = catalog.findCopy(copyId);
        return borrowCopy(member, copy, dueDate);
    }

    public boolean isOverdue(String loanId, LocalDate today) {
        // InMemoryLendingService will keep a map of loans; delegate to it.
        throw new UnsupportedOperationException("Implemented in InMemoryLendingService");
    }

    public void returnLoan(String loanId, LocalDate returnDate) {
        // Same as above – concrete implementation lives in the in‑memory subclass.
        throw new UnsupportedOperationException("Implemented in InMemoryLendingService");
    }
}
