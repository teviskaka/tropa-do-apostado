import discord
from discord import app_commands
from discord.ext import commands
import json
import os
import uuid

# ================== ARQUIVO DB ==================
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

# ================== MODAL DE VALIDAÇÃO (DENTRO DO TICKET) ==================
class ModalValidarCodigo(discord.ui.Modal, title="Resgatar Produto"):
    codigo = discord.ui.TextInput(label="Código Único", placeholder="Resgatar...", required=True)

    async def on_submit(self, interaction: discord.Interaction):
        cod = self.codigo.value.strip()
        if cod in db["cupons"] and not db["cupons"][cod]["usado"]:
            db["cupons"][cod]["usado"] = True
            save_db(db)
            
            owner_role = interaction.guild.get_role(db["config"]["cargo_owner"])
            mention = owner_role.mention if owner_role else "@Owner"
            
            await interaction.response.send_message(
                f"✅ **CÓDIGO VÁLIDO!**\nO usuário {interaction.user.mention} usou o código `{cod}`.\n\n"
                f"🔔 {mention}, envie o produto do cliente aqui!"
            )
        else:
            await interaction.response.send_message("❌ Código inválido ou já usado!", ephemeral=True)

# ================== VIEW DENTRO DO TICKET ==================
class TicketActions(discord.ui.View):
    def __init__(self, cliente_id, tipo):
        super().__init__(timeout=None)
        self.cliente_id = cliente_id
        self.tipo = tipo

    @discord.ui.button(label="Fechar Ticket", style=discord.ButtonStyle.danger, emoji="🔒")
    async def fechar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message("Encerrando canal...")
        await interaction.channel.delete()

    @discord.ui.button(label="Mencionar Membro", style=discord.ButtonStyle.secondary, emoji="👤")
    async def mencionar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_message(f"🔔 Chamando <@{self.cliente_id}>!")

    @discord.ui.button(label="Validar Código", style=discord.ButtonStyle.success, emoji="🔑")
    async def validar(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.tipo == "resgate":
            await interaction.response.send_modal(ModalValidarCodigo())
        else:
            await interaction.response.send_message("❌ Use o ticket de 'Resgate' para validar códigos.", ephemeral=True)

# ================== VIEW PAINEL SUPORTE/RESGATE ==================
class PainelPrincipal(discord.ui.View):
    def __init__(self):
        super().__init__(timeout=None)

    async def abrir_canal(self, interaction: discord.Interaction, tipo):
        cfg = db["config"]
        guild = interaction.guild
        categoria = guild.get_channel(cfg["cat_suporte"])
        
        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.get_role(cfg["cargo_owner"]): discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }

        canal = await guild.create_text_channel(name=f"{tipo}-{interaction.user.name}", category=categoria, overwrites=overwrites)
        
        embed = discord.Embed(title=f"Atendimento: {tipo.upper()}", color=discord.Color.blue())
        if cfg["gif_url"]: embed.set_image(url=cfg["gif_url"])
        
        await canal.send(content=f"{interaction.user.mention} | <@&{cfg['cargo_owner']}>", embed=embed, view=TicketActions(interaction.user.id, tipo))
        await interaction.response.send_message(f"✅ Canal criado: {canal.mention}", ephemeral=True)

    @discord.ui.button(label="Suporte", style=discord.ButtonStyle.primary, emoji="📩", custom_id="sup_btn")
    async def suporte(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.abrir_canal(interaction, "suporte")

    @discord.ui.button(label="Resgatar Compra", style=discord.ButtonStyle.success, emoji="🎁", custom_id="res_btn")
    async def resgatar(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.abrir_canal(interaction, "resgate")

# ================== VIEW CHECKOUT (VENDA) ==================
class AdminActions(discord.ui.View):
    def __init__(self, cliente_id, produto, preco):
        super().__init__(timeout=None)
        self.cliente_id = cliente_id
        self.produto = produto
        self.preco = preco

    @discord.ui.button(label="Aprovar", style=discord.ButtonStyle.success)
    async def approve(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not any(r.id == db["config"]["cargo_owner"] for r in interaction.user.roles):
            return await interaction.response.send_message("❌ Sem permissão.", ephemeral=True)

        codigo_unico = f"Resgatar{str(uuid.uuid4())[:8]}"
        db["cupons"][codigo_unico] = {"usado": False}
        save_db(db)

        membro = interaction.guild.get_member(self.cliente_id)
        await interaction.response.send_message(f"✅ Pagamento Aprovado!\nCódigo do Cliente: `{codigo_unico}`")
        try:
            await membro.send(f"📦 Seu pagamento do produto **{self.produto}** foi aprovado!\nCódigo para resgate: `{codigo_unico}`\nUse o botão de Resgatar no canal de suporte.")
        except: pass

    @discord.ui.button(label="Fechar Carrinho", style=discord.ButtonStyle.secondary)
    async def close(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.channel.delete()

class BuyView(discord.ui.View):
    def __init__(self, produto_nome):
        super().__init__(timeout=None)
        self.produto = produto_nome

    @discord.ui.button(label="Comprar", style=discord.ButtonStyle.success, emoji="🛒")
    async def buy(self, interaction: discord.Interaction, button: discord.ui.Button):
        cfg = db["config"]
        dados = db["produtos"][self.produto]
        guild = interaction.guild
        categoria = guild.get_channel(cfg["cat_suporte"])

        overwrites = {
            guild.default_role: discord.PermissionOverwrite(view_channel=False),
            interaction.user: discord.PermissionOverwrite(view_channel=True, send_messages=True),
            guild.get_role(cfg["cargo_owner"]): discord.PermissionOverwrite(view_channel=True, send_messages=True)
        }
        canal = await guild.create_text_channel(name=f"🛒-{interaction.user.name}", category=categoria, overwrites=overwrites)
        
        embed = discord.Embed(title="💳 Checkout", color=discord.Color.green())
        embed.add_field(name="Produto", value=self.produto)
        embed.add_field(name="Preço", value=f"R$ {dados['preco']}")
        embed.add_field(name="PIX", value=f"`{cfg['pix']}`")
        if dados["imagem"]: embed.set_thumbnail(url=dados["imagem"])

        await canal.send(content=interaction.user.mention, embed=embed, view=AdminActions(interaction.user.id, self.produto, dados['preco']))
        await interaction.response.send_message(f"✅ Carrinho: {canal.mention}", ephemeral=True)

# ================== MODAL CRIAR PRODUTO ==================
class ProdutoModal(discord.ui.Modal, title="Criar Produto"):
    nome = discord.ui.TextInput(label="Nome do Produto")
    desc = discord.ui.TextInput(label="Descrição", style=discord.TextStyle.paragraph)
    preco = discord.ui.TextInput(label="Preço")
    estoque = discord.ui.TextInput(label="Estoque")
    imagem = discord.ui.TextInput(label="Link da Imagem", required=False)

    async def on_submit(self, interaction: discord.Interaction):
        db["produtos"][self.nome.value] = {
            "desc": self.desc.value, "preco": self.preco.value,
            "estoque": self.estoque.value, "imagem": self.imagem.value
        }
        save_db(db)
        await interaction.response.send_message("✅ Produto salvo!", ephemeral=True)

# ================== BOT CLASS ==================
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

# ================== COMANDOS ==================

@bot.tree.command(name="setup_geral", description="Configura PIX, Cargo e Categoria")
async def setup_geral(interaction: discord.Interaction, pix: str, cargo_admin: discord.Role, categoria: discord.CategoryChannel):
    db["config"]["pix"] = pix
    db["config"]["cargo_owner"] = cargo_admin.id
    db["config"]["cat_suporte"] = categoria.id
    save_db(db)
    await interaction.response.send_message("✅ Configurações salvas!", ephemeral=True)

@bot.tree.command(name="enviar_painel", description="Envia o painel de Suporte/Resgate")
async def enviar_painel(interaction: discord.Interaction, canal: discord.TextChannel, gif_url: str):
    db["config"]["gif_url"] = gif_url
    save_db(db)
    embed = discord.Embed(title="Atendimento & Resgate", description="Escolha uma opção abaixo:", color=discord.Color.purple())
    embed.set_image(url=gif_url)
    await canal.send(embed=embed, view=PainelPrincipal())
    await interaction.response.send_message("✅ Painel enviado!", ephemeral=True)

@bot.tree.command(name="editar_painel", description="Edita um painel já enviado")
async def editar_painel(interaction: discord.Interaction, message_id: str, titulo: str, desc: str, gif_url: str):
    msg = await interaction.channel.fetch_message(int(message_id))
    db["config"]["gif_url"] = gif_url
    save_db(db)
    embed = discord.Embed(title=titulo, description=desc, color=discord.Color.purple())
    embed.set_image(url=gif_url)
    await msg.edit(embed=embed, view=PainelPrincipal())
    await interaction.response.send_message("✅ Editado!", ephemeral=True)

@bot.tree.command(name="criar_produto", description="Adiciona produto ao banco")
async def criar_produto(interaction: discord.Interaction):
    await interaction.response.send_modal(ProdutoModal())

@bot.tree.command(name="anunciar_produto", description="Posta o botão de compra")
async def anunciar_produto(interaction: discord.Interaction, nome_do_produto: str, canal: discord.TextChannel):
    if nome_do_produto not in db["produtos"]: return await interaction.response.send_message("❌ Erro.", ephemeral=True)
    dados = db["produtos"][nome_do_produto]
    embed = discord.Embed(title=nome_do_produto, description=dados["desc"], color=discord.Color.green())
    embed.add_field(name="Preço", value=f"R$ {dados['preco']}")
    if dados["imagem"]: embed.set_image(url=dados["imagem"])
    await canal.send(embed=embed, view=BuyView(nome_do_produto))
    await interaction.response.send_message("✅ Anunciado!", ephemeral=True)

# ================== RUN ==================
TOKEN = os.getenv("TOKEN")
bot.run(TOKEN)
