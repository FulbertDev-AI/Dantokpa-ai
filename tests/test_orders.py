
import json

from app.tools import orders


def prepare_storage(tmp_path, monkeypatch):
    products_file = tmp_path / "products.json"
    orders_file = tmp_path / "orders.json"

    products = [
        {
            "id": "P05",
            "name": "Robe en wax",
            "price": 22000,
            "stock": 5,
            "description": "Robe en wax."
        },
        {
            "id": "P03",
            "name": "Sac en raphia",
            "price": 7500,
            "stock": 0,
            "description": "Sac en raphia."
        },
        {
            "id": "P01",
            "name": "Pagne wax 6 yards",
            "price": 12000,
            "stock": 14,
            "description": "Pagne wax.",
        }
    ]

    products_file.write_text(
        json.dumps(products),
        encoding="utf-8"
    )
    orders_file.write_text("[]", encoding="utf-8")

    monkeypatch.setattr(orders, "PRODUCTS_FILE", products_file)
    monkeypatch.setattr(orders, "ORDERS_FILE", orders_file)

    return products_file, orders_file


def set_approvals(monkeypatch, client=True, afi=True):
    monkeypatch.setattr(
        orders,
        "demander_confirmation_client",
        lambda summary: client,
    )
    monkeypatch.setattr(
        orders,
        "demander_approbation_humaine",
        lambda summary: afi,
    )


def test_order_requires_customer_confirmation(tmp_path, monkeypatch):
    prepare_storage(tmp_path, monkeypatch)
    set_approvals(monkeypatch, client=False)

    result = orders.creer_commande(
        customer="Client test",
        items=[{"product_id": "P05", "quantity": 2}],
        delivery_zone="Calavi",
    )

    assert result["success"] is False
    assert "confirmé" in result["message"]
    assert result["stage"] == "customer_confirmation"


def test_order_requires_afi_approval(tmp_path, monkeypatch):
    products_file, orders_file = prepare_storage(tmp_path, monkeypatch)
    set_approvals(monkeypatch, afi=False)

    result = orders.creer_commande(
        customer="Client test",
        items=[{"product_id": "P05", "quantity": 2}],
        delivery_zone="Calavi",
    )

    assert result["success"] is False
    assert "Afi" in result["message"]
    products = json.loads(products_file.read_text(encoding="utf-8"))
    assert products[0]["stock"] == 5
    assert json.loads(orders_file.read_text(encoding="utf-8")) == []


def test_order_success_and_stock_update(tmp_path, monkeypatch):
    products_file, orders_file = prepare_storage(
        tmp_path, monkeypatch
    )
    set_approvals(monkeypatch)

    result = orders.creer_commande(
        customer="Client test",
        items=[{"product_id": "P05", "quantity": 2}],
        delivery_zone="Calavi",
    )

    assert result["success"] is True
    assert result["order"]["subtotal"] == 44000
    assert result["order"]["delivery_fee"] == 2000
    assert result["order"]["total"] == 46000

    products = json.loads(products_file.read_text(encoding="utf-8"))
    saved_orders = json.loads(orders_file.read_text(encoding="utf-8"))

    assert products[0]["stock"] == 3
    assert len(saved_orders) == 1


def test_order_rejects_out_of_stock_product(tmp_path, monkeypatch):
    products_file, orders_file = prepare_storage(
        tmp_path, monkeypatch
    )
    set_approvals(monkeypatch)

    result = orders.creer_commande(
        customer="Client test",
        items=[{"product_id": "P03", "quantity": 1}],
        delivery_zone="Calavi",
    )

    assert result["success"] is False

    products = json.loads(products_file.read_text(encoding="utf-8"))
    saved_orders = json.loads(orders_file.read_text(encoding="utf-8"))

    assert products[1]["stock"] == 0
    assert saved_orders == []


def test_order_rejects_invalid_quantity(tmp_path, monkeypatch):
    prepare_storage(tmp_path, monkeypatch)
    set_approvals(monkeypatch)

    result = orders.creer_commande(
        customer="Client test",
        items=[{"product_id": "P05", "quantity": True}],
        delivery_zone="Calavi",
    )

    assert result["success"] is False
    assert "quantité" in result["message"]


def test_order_does_not_save_when_inventory_write_fails(
    tmp_path, monkeypatch
):
    products_file, orders_file = prepare_storage(tmp_path, monkeypatch)
    set_approvals(monkeypatch)
    real_save_json = orders.save_json

    def fail_products_write(file_path, data):
        if file_path == products_file:
            raise OSError("disk unavailable")
        real_save_json(file_path, data)

    monkeypatch.setattr(orders, "save_json", fail_products_write)
    result = orders.creer_commande(
        customer="Client test",
        items=[{"product_id": "P05", "quantity": 2}],
        delivery_zone="Calavi",
    )

    assert result["success"] is False
    assert "sauvegarder" in result["message"]
    products = json.loads(products_file.read_text(encoding="utf-8"))
    assert products[0]["stock"] == 5
    assert json.loads(orders_file.read_text(encoding="utf-8")) == []


def test_customer_named_afi_cannot_approve_their_own_order(
    tmp_path, monkeypatch
):
    products_file, orders_file = prepare_storage(tmp_path, monkeypatch)
    answers = iter(["o"])
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    monkeypatch.setenv("AFI_APPROVAL_CODE", "private-afi-code")
    monkeypatch.setattr(
        "app.services.approval.getpass.getpass",
        lambda prompt: "not-the-code",
    )

    result = orders.creer_commande(
        customer="Afi",
        items=[{"product_id": "P05", "quantity": 1}],
        delivery_zone="Calavi",
    )

    assert result["success"] is False
    assert result["stage"] == "afi_approval"
    products = json.loads(products_file.read_text(encoding="utf-8"))
    assert products[0]["stock"] == 5
    assert json.loads(orders_file.read_text(encoding="utf-8")) == []


def test_order_omits_out_of_stock_items_and_suggests_alternative(
    tmp_path, monkeypatch
):
    products_file, orders_file = prepare_storage(tmp_path, monkeypatch)
    set_approvals(monkeypatch)

    result = orders.creer_commande(
        customer="Afi",
        items=[
            {"product_id": "P05", "quantity": 2},
            {"product_id": "P03", "quantity": 1},
        ],
        delivery_zone="Calavi",
    )

    assert result["success"] is True
    assert result["order"]["total"] == 46000
    assert [item["product_id"] for item in result["order"]["items"]] == ["P05"]
    assert [item["product_id"] for item in result["order"]["unavailable_items"]] == [
        "P03"
    ]
    assert result["order"]["suggested_alternative"]["product_id"] == "P01"
    products = json.loads(products_file.read_text(encoding="utf-8"))
    assert products[0]["stock"] == 3
    assert products[1]["stock"] == 0
    assert len(json.loads(orders_file.read_text(encoding="utf-8"))) == 1


def test_afi_code_can_authorize_after_client_confirmation(
    tmp_path, monkeypatch
):
    products_file, orders_file = prepare_storage(tmp_path, monkeypatch)
    monkeypatch.setenv("AFI_APPROVAL_CODE", "private-afi-code")
    monkeypatch.setattr("builtins.input", lambda prompt: "o")
    monkeypatch.setattr(
        "app.services.approval.getpass.getpass",
        lambda prompt: "private-afi-code",
    )

    result = orders.creer_commande(
        customer="Client test",
        items=[{"product_id": "P05", "quantity": 1}],
        delivery_zone="Calavi",
    )

    assert result["success"] is True
    products = json.loads(products_file.read_text(encoding="utf-8"))
    assert products[0]["stock"] == 4
    assert len(json.loads(orders_file.read_text(encoding="utf-8"))) == 1
