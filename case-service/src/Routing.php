<?php
declare(strict_types=1);

/** Placeholder routing table. Units and response times are examples until RMB confirms them. */
final class Routing
{
    public const ROUTES = [
        'grievance'           => ['Complaint or grievance',        'Complaints / community relations officer (placeholder)', '5 working days (placeholder)'],
        'illegal_mining'      => ['Report of illegal mining',      'Inspection or enforcement unit (placeholder)',           '48 hours (placeholder)'],
        'license_query'       => ['License or application query',  'Licensing department (placeholder)',                     '3 working days (placeholder)'],
        'export_traceability' => ['Export or traceability issue',  'Trade and traceability team (placeholder)',              '3 working days (placeholder)'],
        'geo_data_request'    => ['Geological data request',       'Geology and laboratory services (placeholder)',          '5 working days (placeholder)'],
        'meeting_request'     => ['Investor meeting request',      'Investment promotion team (placeholder)',                '3 working days (placeholder)'],
        'legal_question'      => ['Legal interpretation question', 'Legal unit (placeholder)',                               '5 working days (placeholder)'],
        'general_enquiry'     => ['General enquiry',               'Information desk (placeholder)',                         '5 working days (placeholder)'],
    ];

    public static function for(string $type): array
    {
        return self::ROUTES[$type] ?? self::ROUTES['general_enquiry'];
    }

    public static function normalise(string $type): string
    {
        return isset(self::ROUTES[$type]) ? $type : 'general_enquiry';
    }
}
