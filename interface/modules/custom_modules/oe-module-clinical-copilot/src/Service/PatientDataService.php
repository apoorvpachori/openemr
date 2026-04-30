<?php

declare(strict_types=1);

namespace OpenEMR\Modules\ClinicalCopilot\Service;

/**
 * Fetches patient data from the OpenEMR MySQL database.
 *
 * Called exclusively from public/api.php, which validates HMAC auth before
 * instantiating this service. Never call this class directly from a web page
 * or from code that hasn't already verified the caller identity.
 *
 * Every method uses PDO prepared statements with `?` placeholders.
 * $pid is always an integer validated upstream — no string interpolation anywhere.
 *
 * Return shape for every method:
 *   Success  → ['status' => 'ok',      'data' => [...]]
 *   No rows  → ['status' => 'no_data', 'message' => 'Human-readable explanation']
 *
 * The 'no_data' shape is NOT an error — it tells the LangGraph agent to say
 * "No X on file" rather than hallucinating data that doesn't exist.
 */
class PatientDataService
{
    public function __construct(private readonly \PDO $pdo) {}

    /**
     * @return array<string, mixed>
     */
    public function getDemographics(int $pid): array
    {
        $stmt = $this->pdo->prepare(
            'SELECT fname, lname, DOB, sex, phone_cell, email
             FROM patient_data
             WHERE pid = ?
             LIMIT 1'
        );
        $stmt->execute([$pid]);
        $row = $stmt->fetch(\PDO::FETCH_ASSOC);

        if (!$row) {
            return ['status' => 'no_data', 'message' => 'Patient not found'];
        }

        return [
            'status' => 'ok',
            'data'   => [
                'name'  => trim(($row['fname'] ?? '') . ' ' . ($row['lname'] ?? '')),
                'dob'   => $row['DOB']        ?? null,
                'sex'   => $row['sex']        ?? null,
                'phone' => $row['phone_cell'] ?? null,
                'email' => $row['email']      ?? null,
            ],
        ];
    }

    /**
     * Active medications, joined with dosage instructions from lists_medication.
     *
     * @return array<string, mixed>
     */
    public function getMedications(int $pid): array
    {
        $stmt = $this->pdo->prepare(
            "SELECT l.title, l.begdate, l.enddate,
                    lm.drug_dosage_instructions, lm.usage_category_title
             FROM lists l
             LEFT JOIN lists_medication lm ON lm.list_id = l.id
             WHERE l.pid = ? AND l.type = 'medication' AND l.activity = 1
             ORDER BY l.begdate DESC"
        );
        $stmt->execute([$pid]);
        $rows = $stmt->fetchAll(\PDO::FETCH_ASSOC);

        if (empty($rows)) {
            return ['status' => 'no_data', 'message' => 'No active medications on file'];
        }

        return ['status' => 'ok', 'data' => $rows];
    }

    /**
     * Five most recent encounters — enough context without overwhelming the LLM.
     *
     * @return array<string, mixed>
     */
    public function getEncounters(int $pid): array
    {
        $stmt = $this->pdo->prepare(
            'SELECT date, reason, encounter_type_description, provider_id
             FROM form_encounter
             WHERE pid = ?
             ORDER BY date DESC
             LIMIT 5'
        );
        $stmt->execute([$pid]);
        $rows = $stmt->fetchAll(\PDO::FETCH_ASSOC);

        if (empty($rows)) {
            return ['status' => 'no_data', 'message' => 'No encounters on file'];
        }

        return ['status' => 'ok', 'data' => $rows];
    }

    /**
     * Ten most recent lab results with reference ranges and abnormal flags.
     *
     * Joins: procedure_order → procedure_report → procedure_result
     * procedure_result.date is the result date (confirmed from schema).
     *
     * @return array<string, mixed>
     */
    public function getLabs(int $pid): array
    {
        $stmt = $this->pdo->prepare(
            'SELECT pr.result_text, pr.result, pr.units, pr.range,
                    pr.abnormal, pr.result_status, pr.date
             FROM procedure_order po
             JOIN procedure_report prp ON prp.procedure_order_id = po.procedure_order_id
             JOIN procedure_result pr  ON pr.procedure_report_id  = prp.procedure_report_id
             WHERE po.patient_id = ?
             ORDER BY pr.date DESC
             LIMIT 10'
        );
        $stmt->execute([$pid]);
        $rows = $stmt->fetchAll(\PDO::FETCH_ASSOC);

        if (empty($rows)) {
            return ['status' => 'no_data', 'message' => 'No lab results on file'];
        }

        return ['status' => 'ok', 'data' => $rows];
    }

    /**
     * Active medical problems with ICD codes.
     *
     * @return array<string, mixed>
     */
    public function getProblems(int $pid): array
    {
        $stmt = $this->pdo->prepare(
            "SELECT title, diagnosis, begdate, enddate
             FROM lists
             WHERE pid = ? AND type = 'medical_problem' AND activity = 1
             ORDER BY begdate DESC"
        );
        $stmt->execute([$pid]);
        $rows = $stmt->fetchAll(\PDO::FETCH_ASSOC);

        if (empty($rows)) {
            return ['status' => 'no_data', 'message' => 'No active problems on file'];
        }

        return ['status' => 'ok', 'data' => $rows];
    }

    /**
     * Active allergies with reaction and severity.
     *
     * @return array<string, mixed>
     */
    public function getAllergies(int $pid): array
    {
        $stmt = $this->pdo->prepare(
            "SELECT title, reaction, severity_al, verification
             FROM lists
             WHERE pid = ? AND type = 'allergy' AND activity = 1
             ORDER BY title ASC"
        );
        $stmt->execute([$pid]);
        $rows = $stmt->fetchAll(\PDO::FETCH_ASSOC);

        if (empty($rows)) {
            return ['status' => 'no_data', 'message' => 'No allergies on file'];
        }

        return ['status' => 'ok', 'data' => $rows];
    }
}
