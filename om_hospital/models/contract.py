from odoo import api, fields, models
from odoo.exceptions import UserError, ValidationError


class HospitalContract(models.Model):
    _name = "hospital.contract"
    _description = "Company Contract"
    _inherit = ["mail.thread", "mail.activity.mixin"]
    _order = "date_start desc, id desc"
    _rec_names_search = ["name", "partner_id.name"]

    name = fields.Char(
        string="Reference",
        required=True,
        copy=False,
        readonly=True,
        default="New",
        help="Unique reference generated automatically.",
    )
    partner_id = fields.Many2one(
        "res.partner",
        string="Company",
        required=True,
        index=True,
        ondelete="restrict",
        tracking=True,
        domain="[('is_company', '=', True)]",
        help="Company or insurer. Patients whose contact belongs to this company are covered.",
    )
    date_start = fields.Date(
        string="Start Date",
        required=True,
        default=fields.Date.today,
        tracking=True,
    )
    date_end = fields.Date(
        string="End Date",
        tracking=True,
        help="Leave empty for an open-ended contract.",
    )
    state = fields.Selection(
        [("draft", "Draft"), ("active", "Active"), ("cancel", "Cancelled")],
        string="Status",
        default="draft",
        index=True,
        tracking=True,
    )
    default_discount = fields.Float(
        string="Default Discount (%)",
        digits="Discount",
        tracking=True,
        help="Discount applied to services whose category has no specific rule below.",
    )
    company_share = fields.Float(
        string="Company Pays (%)",
        default=80.0,
        tracking=True,
        help="Share of the discounted amount invoiced to the company. "
        "The patient is invoiced the remainder.",
    )
    line_ids = fields.One2many(
        "hospital.contract.line",
        "contract_id",
        string="Category Discounts",
        copy=True,
    )
    patient_count = fields.Integer(
        string="Patient Count",
        compute="_compute_counts",
        help="Patients whose contact belongs to the contract company.",
    )
    order_count = fields.Integer(
        string="Order Count",
        compute="_compute_counts",
        help="Quotations and sales orders billed under this contract.",
    )

    _name_uniq = models.Constraint("UNIQUE(name)", "The contract reference must be unique.")
    _discount_range = models.Constraint(
        "CHECK(default_discount >= 0 AND default_discount <= 100)",
        "The default discount must be between 0 and 100.",
    )
    _share_range = models.Constraint(
        "CHECK(company_share >= 0 AND company_share <= 100)",
        "The company share must be between 0 and 100.",
    )
    _dates_check = models.Constraint(
        "CHECK(date_end IS NULL OR date_end >= date_start)",
        "The end date cannot be before the start date.",
    )

    # ------------------------------------------------------------------
    # Compute methods
    # ------------------------------------------------------------------

    @api.depends("partner_id")
    def _compute_counts(self):
        patient_counts = {
            company.id: count
            for company, count in self.env["res.partner"]._read_group(
                [("parent_id", "in", self.partner_id.ids), ("is_patient", "=", True)],
                groupby=["parent_id"],
                aggregates=["__count"],
            )
        }
        order_counts = {
            contract.id: count
            for contract, count in self.env["sale.order"]._read_group(
                [("hospital_contract_id", "in", self.ids)],
                groupby=["hospital_contract_id"],
                aggregates=["__count"],
            )
        }
        for rec in self:
            rec.patient_count = patient_counts.get(rec.partner_id.id, 0)
            rec.order_count = order_counts.get(rec.id, 0)

    # ------------------------------------------------------------------
    # Constraints
    # ------------------------------------------------------------------

    @api.constrains("partner_id", "date_start", "date_end", "state")
    def _check_no_overlapping_active_contract(self):
        """A company can only have one active contract at any date."""
        for rec in self.filtered(lambda c: c.state == "active"):
            others = self.search(
                [
                    ("id", "!=", rec.id),
                    ("partner_id", "=", rec.partner_id.id),
                    ("state", "=", "active"),
                ]
            )
            for other in others:
                other_ends_after_start = not other.date_end or other.date_end >= rec.date_start
                starts_before_end = not rec.date_end or other.date_start <= rec.date_end
                if other_ends_after_start and starts_before_end:
                    raise ValidationError(
                        self.env._(
                            "%(company)s already has an active contract (%(other)s) "
                            "overlapping these dates.",
                            company=rec.partner_id.name,
                            other=other.name,
                        )
                    )

    # ------------------------------------------------------------------
    # Discount engine (used by sale.order.line)
    # ------------------------------------------------------------------

    @api.model
    def _get_contract_for_partner(self, partner, on_date=None):
        """Return the active contract of the company a patient contact belongs to."""
        company = partner.parent_id
        if not company:
            return self.browse()
        on_date = on_date or fields.Date.context_today(self)
        return self.search(
            [
                ("partner_id", "=", company.id),
                ("state", "=", "active"),
                ("date_start", "<=", on_date),
                "|",
                ("date_end", "=", False),
                ("date_end", ">=", on_date),
            ],
            limit=1,
        )

    def _get_category_discount(self, product):
        """Discount for a product: the most specific matching category rule, else the default."""
        self.ensure_one()
        by_category = {line.category_id.id: line.discount for line in self.line_ids}
        category = product.categ_id
        while category:
            if category.id in by_category:
                return by_category[category.id]
            category = category.parent_id
        return self.default_discount

    def _get_line_discount(self, product, payer):
        """Discount (%) of the line on the order billed to ``payer`` ('patient' or 'company').

        The contract discount reduces the price first; the payer then carries only
        their share of the discounted amount, so both orders add up to the contract price.
        """
        self.ensure_one()
        price_factor = 1 - self._get_category_discount(product) / 100.0
        company_share = self.company_share / 100.0
        share = company_share if payer == "company" else 1 - company_share
        return (1 - price_factor * share) * 100.0

    # ------------------------------------------------------------------
    # CRUD overrides
    # ------------------------------------------------------------------

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if vals.get("name", "New") == "New":
                vals["name"] = self.env["ir.sequence"].next_by_code("hospital.contract") or "New"
        return super().create(vals_list)

    @api.ondelete(at_uninstall=False)
    def _unlink_except_active(self):
        if any(rec.state == "active" for rec in self):
            raise UserError(self.env._("Cancel an active contract instead of deleting it."))

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_activate(self):
        for rec in self:
            if rec.state != "draft":
                raise UserError(self.env._("Only draft contracts can be activated."))
            rec.state = "active"
            rec.message_post(body=self.env._("Contract activated."))

    def action_cancel(self):
        self.write({"state": "cancel"})

    def action_draft(self):
        self.write({"state": "draft"})

    def action_view_patients(self):
        self.ensure_one()
        return {
            "name": self.env._("Patients"),
            "type": "ir.actions.act_window",
            "res_model": "hospital.patient",
            "view_mode": "list,form",
            "domain": [("partner_id.parent_id", "=", self.partner_id.id)],
        }

    def action_view_orders(self):
        self.ensure_one()
        return {
            "name": self.env._("Sales Orders"),
            "type": "ir.actions.act_window",
            "res_model": "sale.order",
            "view_mode": "list,form",
            "domain": [("hospital_contract_id", "=", self.id)],
        }
