import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import uuid

# ================== BANCO DE DADOS ==================
DB_FILE = "database.json"

def load_db():
    if not os.path.exists(DB_FILE):
        return {
            "config": {
                "pix": "Não configurado",
                "cargo_owner": None,
                "cat_suporte": None,
                "gif_url": ""
            },
            "produtos": {},
            "cupons": {}
        }
    with open(DB_FILE, "r", encoding="utf-8") as f:
        return json.load(f)

def save_db(data):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

db = load_db()

# ================== VIEW INTERNA DO TICKET/ENTREGA ==================
class TicketActions(discord.ui.View):
    def __init__(self, cliente_id):
        super().__init__(timeout=None)
        self.cliente_id = cliente_id

    @discord.ui.button(label="Fechar Ticket", style=discord.ButtonStyle.danger, emoji="🔒")
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Encerrando canal em 3 segundos...")
        await interaction.channel.delete()

    @discord.ui.button(label="Mencionar Membro", style=discord.ButtonStyle.secondary, emoji="👤")
    async def mencionar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"🔔 Chamando <@{self.cliente_id}>!")

# ================== MODAL DE RESGATE (ABRE O CANAL SE O COD FOR CERTO) ==================
class ModalResgateInicial(discord.ui.Modal, title="Resgatar Produto"):
    codigo = discord.ui.TextInput(label="Insira seu código único", placeholder="Resgatar...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        cod = self.codigo.value.strip()
        cfg = db["config"]

        if cod in db["cupons"] and not db["cupons"][cod]["usado"]:
            # Marcar código como usado
            db["cupons"][cod]["usado"] = True
            save_db(db)

            # Criar Canal de Entrega
            guild = interaction.guild
            categoria = guild.get_channel(int(cfg["cat_suporte"]))
            cargo_staff = guild.get_role(int(cfg["cargo_owner"]))

            overwrites = {
                guild.default_role: discord.PermissionOverwrite(view_channel=False),
                interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
                cargo_staff: discord.PermissionOverwrite(view_channel=True, send_messages=True)
            }

            canal = await guild.create_text_channel(name=f"entrega-{interaction.user.name}", category=categoria, overwrites=overwrites)
            
            embed = discord.Embed(
                title="✅ Código Validado!",
                description=f"O código `{cod}` foi aceito.\n\n{cargo_staff.mention}, envie o produto do cliente aqui!",
                color=discord.Color.green()
            )
            if cfg["gif_url"]: embed.set_image(url=cfg["gif_url"])

            await canal.send(content=f"{interaction.user.mention} | {cargo_staff.mention}", embed=embed, view=TicketActions(interaction.user.id))
            await interaction.response.send_message(f"✅ Sucesso! Canal de entrega: {canal.mention}", ephemeral=True)
        else:
            await interaction.response.send_message("❌ Código inválido ou já utilizado!", ephemeral=True)

# ================== PAINEL DE SUPORTE E RESGATE ==================
class PainelPrincipal(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    @discord.ui.button(label="Suporte", style=discord.ButtonStyle.primary, emoji="📩", custom_id="btn_sup_geral")
    async def suporte(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = db["config"]
        if not cfg["cat_suporte"]: return await interaction.response.send_message("Não configurado!", ephemeral=True)

        guild = interaction.guild
        categoria = guild.get_channel(int(cfg["cat_suporte"]))
        cargo_staff = guild.get_role(int(cfg["cargo_owner"]))

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            cargo_staff: discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }

        canal = await guild.create_text_channel(name=f"suporte-{interaction.user.name}", category=categoria, overwrites=overwrites)
        embed = discord.Embed(title="Atendimento", description="Aguarde o suporte.", color=discord.Color.blue())
        if cfg["gif_url"]: embed.set_image(url=cfg["gif_url"])

        await canal.send(content=f"{interaction.user.mention} | {cargo_staff.mention}", embed=embed, view=TicketActions(interaction.user.id))
        await interaction.response.send_message(f"✅ Canal criado: {canal.mention}", ephemeral=True)

    @discord.ui.button(label="Resgatar Compra", style=discord.ButtonStyle.success, emoji="🎁", custom_id="btn_res_geral")
    async def resgatar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(ModalResgateInicial())

# ================== SISTEMA DE VENDAS (CARRINHO E PRODUTOS) ==================
class AdminActions(discord.ui.View):
    def __init__(self, cliente_id, produto):
        super().__init__(timeout=None)
        self.cliente_id = cliente_id
        self.produto = produto

    @discord.ui.button(label="Aprovar Pagamento", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(r.id == db["config"]["cargo_owner"] for r in interaction.user.roles):
            return await interaction.response.send_message("Sem permissão!", ephemeral=True)

        codigo = f"Resgatar{str(uuid.uuid4())[:8]}"
        db["cupons"][codigo] = {"usado": False}
        save_db(db)
        await interaction.response.send_message(f"✅ Pagamento Aprovado!\nCódigo Gerado: `{codigo}`")

    @discord.ui.button(label="Fechar Carrinho", style=discord.ButtonStyle.danger)
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.delete()

class BuyView(discord.ui.View):
    def __init__(self, produto_nome):
        super().__init__(timeout=None)
        self.produto = produto_nome

    @discord.ui.button(label="Comprar", style=discord.ButtonStyle.success, emoji="🛒")
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = db["config"]
        dados = db["produtos"][self.produto]
        categoria = interaction.guild.get_channel(int(cfg["cat_suporte"]))
        
        overwrites = {
            interaction.guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            interaction.guild.get_role(int(cfg["cargo_owner"])): discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        canal = await interaction.guild.create_text_channel(name=f"🛒-{interaction.user.name}", category=categoria, overwrites=overwrites)
        embed = discord.Embed(title="💳 Checkout", description=f"**Produto:** {self.produto}\n**Valor:** R$ {dados['preco']}\n**PIX:** `{cfg['pix']}`", color=0x2ecc71)
        if dados["imagem"]: embed.set_thumbnail(url=dados["imagem"])
        await canal.send(content=interaction.user.mention, embed=embed, view=AdminActions(interaction.user.id, self.produto))
        await interaction.response.send_message(f"✅ Carrinho criado: {canal.mention}", ephemeral=True)

# ================== BOT E COMANDOS ==================
class MyBot(commands.Bot):
    def __init__(self):
        intents = discord.Intents.default()
        intents.message_content = True
        intents.members = True
        super().__init__(command_prefix="!", intents=intents)

    async def setup_hook(self):
        self.add_view(PainelPrincipal())
        await self.tree.sync()

bot = MyBot()

@bot.tree.command(name="setup_geral", description="Configura PIX, Staff e Categoria")
async def setup_geral(interaction: discord.Interaction, pix: str, cargo_admin: discord.Role, categoria: discord.CategoryChannel):
    db["config"].update({"pix": pix, "cargo_owner": cargo_admin.id, "cat_suporte": categoria.id})
    save_db(db)
    await interaction.response.send_message("✅ Configurações salvas!", ephemeral=True)

@bot.tree.command(name="editar_categoria", description="Edita a categoria dos canais")
async def editar_categoria(interaction: discord.Interaction, nova_categoria: discord.CategoryChannel):
    db["config"]["cat_suporte"] = nova_categoria.id
    save_db(db)
    await interaction.response.send_message(f"✅ Categoria alterada!", ephemeral=True)

@bot.tree.command(name="enviar_painel", description="Envia o painel Suporte/Resgate")
async def enviar_painel(interaction: discord.Interaction, canal: discord.TextChannel, gif_url: str):
    db["config"]["gif_url"] = gif_url
    save_db(db)
    embed = discord.Embed(title="Central de Atendimento", description="📩 Suporte\n🎁 Resgate de Produto", color=0x2b2d31)
    embed.set_image(url=gif_url)
    await canal.send(embed=embed, view=PainelPrincipal())
    await interaction.response.send_message("✅ Painel enviado!", ephemeral=True)

@bot.tree.command(name="editar_painel", description="Edita a mensagem do painel")
async def editar_painel(interaction: discord.Interaction, message_id: str, titulo: str, desc: str, gif_url: str):
    msg = await interaction.channel.fetch_message(int(message_id))
    db["config"]["gif_url"] = gif_url
    save_db(db)
    embed = discord.Embed(title=titulo, description=desc, color=0x2b2d31)
    embed.set_image(url=gif_url)
    await msg.edit(embed=embed, view=PainelPrincipal())
    await interaction.response.send_message("✅ Painel atualizado!", ephemeral=True)

@bot.tree.command(name="criar_produto", description="Adiciona um produto")
async def criar_produto(interaction: discord.Interaction, nome: str, preco: str, desc: str, imagem: str = None):
    db["produtos"][nome] = {"desc": desc, "preco": preco, "imagem": imagem}
    save_db(db)
    await interaction.response.send_message(f"✅ Produto {nome} criado!", ephemeral=True)

@bot.tree.command(name="anunciar_produto", description="Anuncia produto com botão de compra")
async def anunciar_produto(interaction: discord.Interaction, nome_do_produto: str, canal: discord.TextChannel):
    if nome_do_produto not in db["produtos"]: return await interaction.response.send_message("❌ Erro.", ephemeral=True)
    dados = db["produtos"][nome_do_produto]
    embed = discord.Embed(title=nome_do_produto, description=dados["desc"], color=0x2ecc71)
    if dados["imagem"]: embed.set_image(url=dados["imagem"])
    await canal.send(embed=embed, view=BuyView(nome_do_produto))
    await interaction.response.send_message("✅ Anúncio feito!", ephemeral=True)

TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
