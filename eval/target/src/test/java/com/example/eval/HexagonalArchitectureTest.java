package com.example.eval;

import com.tngtech.archunit.core.domain.JavaClasses;
import com.tngtech.archunit.core.importer.ClassFileImporter;
import com.tngtech.archunit.core.importer.ImportOption;
import org.junit.jupiter.api.Test;

import static com.tngtech.archunit.lang.syntax.ArchRuleDefinition.noClasses;

/**
 * Architecture gate (M4) — runs inside `mvn test` as the dual-assessment oracle.
 * The agent's code must not just pass functional tests, it must keep the
 * hexagonal boundaries: the domain stays the innermost, dependency-free core.
 *
 * These are protected (immutable) rules: the agent implements production code to
 * satisfy them and may not edit this file.
 */
class HexagonalArchitectureTest {

    private final JavaClasses classes = new ClassFileImporter()
            .withImportOption(ImportOption.Predefined.DO_NOT_INCLUDE_TESTS)
            .importPackages("com.example.eval");

    @Test
    void domainDoesNotDependOnApplicationOrAdapters() {
        noClasses().that().resideInAPackage("..domain..")
                .should().dependOnClassesThat().resideInAnyPackage("..application..", "..adapters..")
                .because("the domain is the innermost layer and must stay framework- and infra-free")
                .check(classes);
    }

    @Test
    void applicationDoesNotDependOnAdapters() {
        noClasses().that().resideInAPackage("..application..")
                .should().dependOnClassesThat().resideInAPackage("..adapters..")
                .because("application talks to the outside only through ports, never concrete adapters")
                .check(classes);
    }
}
