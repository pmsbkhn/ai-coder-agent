package com.example.library.lending;

import static org.junit.jupiter.api.Assertions.*;
import java.time.LocalDate;
import java.util.UUID;
import org.junit.jupiter.api.Test;

class LoanCreationCopyNotAvailableTest {
    @Test
    void cannotLoanNonAvailableCopy() {
        // setup catalog with a copy already ON_LOAN
        CatalogService catalog = new InMemoryCatalogService();
        Title title = new Title(UUID.randomUUID(), "ISBN-456", "Clean Architecture");
        catalog.addTitle(title);
        Copy copy = catalog.createCopy(title.getId());
        // simulate that the copy is already on loan
        copy.setStatus(CopyStatus.ON_LOAN);
        // member is active and has capacity
        MemberService members = new InMemoryMemberService();
        Member member = members.register("Alice");
        LendingService lending = new InMemoryLendingService(catalog, members);
        // action & assert
        DomainException ex = assertThrows(DomainException.class,
            () -> lending.createLoan(member.getId(), copy.getId(), LocalDate.now()));
        assertEquals(DomainException.Code.COPY_NOT_AVAILABLE, ex.getCode());
    }
}
