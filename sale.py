# -*- coding: utf-8 -*-
"""
    sale.py

    :copyright: (c) 2014 by Openlabs Technologies & Consulting (P) Limited
    :license: BSD, see LICENSE for more details.
"""
from decimal import Decimal

from trytond.model import fields
from trytond.pool import PoolMeta, Pool
from trytond.transaction import Transaction

__all__ = ['SaleLine', 'Sale']
__metaclass__ = PoolMeta


class Sale:
    "Sale"
    __name__ = 'sale.sale'

    package_weight = fields.Function(
        fields.Numeric("Package weight", digits=(16,  2)),
        'get_package_weight'
    )

    weight_uom = fields.Function(
        fields.Many2One('product.uom', 'Weight UOM'),
        'get_weight_uom'
    )

    def get_weight_uom(self, name):
        """
        Returns weight uom for the package
        """
        return self._get_weight_uom().id

    def _get_weight_uom(self):
        """
        Returns Pound as default value for uom

        Downstream module can override this method to change weight uom as per
        carrier
        """
        UOM = Pool().get('product.uom')

        return UOM.search([('symbol', '=', 'lb')])[0]

    def get_package_weight(self, name):
        """
        Returns sum of weight associated with each line
        """
        weight_uom = self._get_weight_uom()
        return self._get_package_weight(weight_uom)

    def _get_package_weight(self, uom):
        """
        Returns sum of weight associated with package
        """
        return sum(
            map(
                lambda line: line.get_weight(uom, silent=True),
                self.lines
            )
        )

    def _get_ship_from_address(self):
        """
        Usually the warehouse from which you ship
        """
        return self.warehouse.address

    def create_shipment(self, shipment_type):
        """
        Create shipments for sale with sale in context. Sale in transaction
        can be used to get defaults from sale while creating shipment
        """
        with Transaction().set_context(sale=self.id):
            return super(Sale, self).create_shipment(shipment_type)

    def add_shipping_line(self, shipment_cost, description):
        """
        This method takes shipping_cost and description as arguments and writes
        a shipping line. It deletes any previous shipping lines which have
        a shipment_cost.
        :param shipment_cost: The shipment cost calculated according to carrier
        :param description: Shipping line description
        """
        self.__class__.write([self], {
            'lines': [
                ('create', [{
                    'type': 'line',
                    'product': self.carrier.carrier_product.id,
                    'description': description,
                    'quantity': 1,  # XXX
                    'unit': self.carrier.carrier_product.sale_uom.id,
                    'unit_price': shipment_cost,
                    'shipment_cost': shipment_cost,
                    'amount': shipment_cost,
                    'taxes': [],
                    'sequence': 9999,  # XXX
                }]),
                ('delete', [
                    line for line in self.lines if line.shipment_cost
                ]),
            ]
        })


class SaleLine:
    'Sale Line'
    __name__ = 'sale.line'

    @classmethod
    def __setup__(cls):
        super(SaleLine, cls).__setup__()
        cls._error_messages.update({
            'weight_required': 'Weight is missing on the product %s',
        })

    def get_weight(self, weight_uom, silent=False):
        """
        Returns weight as required for carriers

        :param weight_uom: Weight uom used by carriers
        :param silent: Raise error if not silent
        """
        ProductUom = Pool().get('product.uom')

        if not self.product or self.quantity <= 0 or \
                self.product.type == 'service':
            return Decimal('0')

        if not self.product.weight:
            if silent:
                return Decimal('0')
            self.raise_user_error(
                'weight_required',
                error_args=(self.product.name,)
            )

        # Find the quantity in the default uom of the product as the weight
        # is for per unit in that uom
        if self.unit != self.product.default_uom:
            quantity = ProductUom.compute_qty(
                self.unit,
                self.quantity,
                self.product.default_uom
            )
        else:
            quantity = self.quantity

        weight = self.product.weight * quantity

        # Compare product weight uom with the weight uom used by carrier
        # and calculate weight if botth are not same
        if self.product.weight_uom.symbol != weight_uom.symbol:
            weight = ProductUom.compute_qty(
                self.product.weight_uom,
                weight,
                weight_uom,
            )

        return Decimal(weight)
